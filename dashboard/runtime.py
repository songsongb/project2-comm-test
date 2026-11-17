"""Process-lifetime services, independent of Streamlit reruns and LLM latency."""
from collections import deque
import csv
import io
import json
import os
from pathlib import Path
import queue
import threading
import time
from .anomaly_detector import AnomalyDetector
from .command_controller import CommandController
from .config import DATA_DIR
from .diagnosis_manager import DiagnosisManager
from .metrics import summarize
from .protocol_parser import parse
from .serial_manager import SerialManager
from .state_manager import StateManager
from .storage import Storage


def csv_bytes(rows):
    if not rows:
        return b""
    out = io.StringIO(newline="")
    fields = list(dict.fromkeys(k for row in rows for k in row))
    writer = csv.DictWriter(out, fieldnames=fields)
    writer.writeheader()
    writer.writerows(rows)
    return out.getvalue().encode("utf-8-sig")


class Runtime:
    def __init__(self, data_dir=None, client=None):
        self.data_dir = Path(data_dir or os.environ.get("DASHBOARD_DATA_DIR", DATA_DIR))
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage = Storage(self.data_dir / "dashboard.sqlite3")
        self.state = StateManager(self.storage)
        self.serial = SerialManager(self.receive, self.state.set_connection)
        self.controller = CommandController(self.state, self.serial, self.storage)
        self.detector = AnomalyDetector()
        self.diagnosis = DiagnosisManager(self.storage, client)
        self.queue = queue.Queue(maxsize=20000)
        self.lock = threading.RLock()
        self.mode = "live"
        self.replay = None
        self.auto_diagnose = False
        self.queue_drops = 0
        self.error = None
        self.stop = threading.Event()
        self.anomalies = deque(maxlen=200)
        self.closed = False
        self.thread = threading.Thread(target=self._run, name="log-processing", daemon=True)
        self.thread.start()

    def receive(self, record):
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            self.queue_drops += 1  # Visible PC-side loss, never an invented MCU counter.

    def process(self, record):
        with self.lock:
            self.state.ingest(parse(record))
            metric = self.state.metric_rows[-1] if record.kind == "STAT" else None
            alerts = self.detector.check(record, metric)
            for alert in alerts:
                self.anomalies.append(alert)
                self.storage.save("anomaly", alert)
                if self.auto_diagnose:
                    try:
                        self.request_diagnosis(alert)
                    except ValueError as exc:
                        self.error = str(exc)
            self.controller.on_record(record)

    def _run(self):
        last_poll = 0
        while not self.stop.is_set():
            try:
                r = self.queue.get(timeout=.1)
            except queue.Empty:
                r = None
            try:
                if r:
                    self.process(r)
                if time.monotonic() - last_poll >= 1:
                    last_poll = time.monotonic()
                    if self.mode == "live":
                        self.controller.query()
                    self.controller.tick()
            except Exception as exc:
                self.error = f"{type(exc).__name__}: {exc}"
            finally:
                if r:
                    self.queue.task_done()

    def switch_mode(self, mode):
        if mode not in ("live", "demo", "replay"):
            raise ValueError("입력 모드 오류")
        # Stop producers first. Then drain accepted records and reset only memory.
        if self.replay:
            self.replay.close()
            self.replay = None
        self.serial.close()
        self.queue.join()
        with self.lock:
            self.state.stop_experiment()
            if self.controller.current and self.controller.current["status"] in ("queued", "sent", "awaiting_verification"):
                self.controller._finish(self.controller.current, "unknown", "입력 모드 변경")
            self.state = StateManager(self.storage)
            self.serial.status = self.state.set_connection
            self.controller = CommandController(self.state, self.serial, self.storage)
            self.detector = AnomalyDetector()
            self.anomalies.clear()
            self.mode = mode

    def evidence(self, required_ids=()):
        with self.state.lock:
            records = list(self.state.records)
            rows = list(self.state.metric_rows)
        selected = [r for r in records if r.id in required_ids]
        selected += [r for r in records[-50:] if r not in selected and r.kind not in ("RAW", "HEADER", "TRACE_DATA")]
        evidence = [{"id": r.id, "device": r.device, "source": r.source,
                     "fields": {**r.data, "kind": r.kind, "session": r.session,
                                "pc_received_at": r.received_at, "raw": r.raw}}
                    for r in selected]
        for i, row in enumerate(summarize(rows)):
            evidence.append({"id": f"summary-{i}", "device": "window", "source": row["source"], "fields": row})
        return evidence

    def request_diagnosis(self, anomaly):
        evidence = self.evidence(anomaly["evidence_ids"])
        if not any(e["id"] in anomaly["evidence_ids"] for e in evidence):
            raise ValueError("근거가 메모리 보존 범위를 벗어났습니다. 저장 이력을 확인하세요")
        return self.diagnosis.submit(anomaly["code"], evidence, anomaly_id=anomaly["id"])

    def close(self):
        if self.closed:
            return
        self.closed = True
        if self.replay:
            self.replay.close()
        self.serial.close()
        self.queue.join()
        self.stop.set()
        self.thread.join(timeout=2)
        self.diagnosis.close()
        # Keep SQLite open if an in-flight diagnosis still needs to persist its result.
        if not self.diagnosis.thread.is_alive():
            self.storage.close()
