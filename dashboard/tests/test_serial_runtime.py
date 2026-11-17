from collections import deque
import queue
import subprocess
import sys
import threading
import time
from pathlib import Path
import pytest
from dashboard.serial_manager import SerialManager, PortLock
from dashboard.runtime import Runtime
from dashboard.config import ROOT
from dashboard.replay import read_jsonl, to_record


def until(predicate, seconds=3):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if predicate():
            return
        time.sleep(.01)
    assert predicate()


class FakePort:
    def __init__(self):
        self.data = queue.Queue()
        self.writes = []
        self.closed = False

    def read(self, size):
        try:
            result = self.data.get(timeout=.01)
        except queue.Empty:
            return b""
        if isinstance(result, Exception):
            raise result
        return result

    def write(self, data):
        self.writes.append(data)
        return len(data)

    def close(self):
        self.closed = True


def test_multiport_reader_partial_lines_disconnect_reconnect(tmp_path):
    received, statuses = [], []
    created = {"test-window": [], "test-door": []}
    def factory(port):
        fake = FakePort()
        created[port].append(fake)
        return fake
    manager = SerialManager(received.append, lambda *args: statuses.append(args), factory)
    try:
        manager.connect("window", "test-window")
        manager.connect("door", "test-door")
        until(lambda: all(created.values()))
        w, d = created["test-window"][0], created["test-door"][0]
        w.data.put(b"PLOT,20")
        w.data.put(b"00,3000\r\n")
        d.data.put(b"2000,2000,2000,0,1,0,0,0\n")
        until(lambda: len(received) == 2)
        assert {r.device for r in received} == {"window", "door"}
        with pytest.raises(ValueError):
            manager.connect("hub", "test-window")
        w.data.put(IOError("cable removed"))
        d.data.put(b"3000,2000,2000,0,1,0,0,0\n")
        until(lambda: len(received) == 3)
        until(lambda: len(created["test-window"]) >= 2)
        created["test-window"][-1].data.put(b"PLOT,4000,3010\n")
        until(lambda: len(received) == 4)
        assert any(s[0] == "window" and not s[1] for s in statuses)
    finally:
        manager.close()


def test_port_lock_cross_process():
    lock = PortLock("test-cross-process-lock")
    lock.acquire()
    try:
        script = "from dashboard.serial_manager import PortLock; PortLock('test-cross-process-lock').acquire()"
        result = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True)
        assert result.returncode != 0 and "RuntimeError" in result.stderr
    finally:
        lock.release()
    other = PortLock("test-cross-process-lock")
    other.acquire()
    other.release()


def test_full_synthetic_fixture_six_conditions_trace_and_raw_storage(tmp_path):
    rt = Runtime(tmp_path)
    try:
        entries = read_jsonl((ROOT / "samples/synthetic_demo.jsonl").read_text())
        for entry in entries:
            rt.process(to_record(entry, demo=True))
        from dashboard.metrics import summarize
        summary = summarize(list(rt.state.metric_rows))
        assert len(summary) == 6
        assert all(r["source"] == "demo" for r in summary)
        trace = rt.state.snapshot()["traces"][-1]
        assert trace["status"] == "complete"
        assert sum(r["gap"] for r in trace["rows"]) == 4
        assert len(rt.storage.raw_records()) == len(entries)
        assert not rt.error
    finally:
        rt.close()


def test_real_pyserial_pseudoterminal_roundtrip():
    if sys.platform == "win32":
        pytest.skip("Linux PTY test; Windows hardware COM needs physical verification")
    import os
    import pty
    import select
    master, slave = pty.openpty()
    path = os.ttyname(slave)
    received, status = [], []
    manager = SerialManager(received.append, lambda *args: status.append(args))
    try:
        manager.connect("window", path)
        until(lambda: manager.workers["window"].connected)
        os.write(master, b"PLOT,1000,3000\r\n")
        until(lambda: bool(received))
        assert received[0].raw == "PLOT,1000,3000"
        manager.enqueue("window", lambda ser: ser.write(b"PLOT\r\n"))
        assert select.select([master], [], [], 2)[0]
        assert b"PLOT\r\n" in os.read(master, 100)
    finally:
        manager.close()
        os.close(master)
        os.close(slave)
