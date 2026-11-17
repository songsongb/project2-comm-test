"""One reader/writer per port. OS lock covers other Dashboard processes too."""
import hashlib
import os
from pathlib import Path
import queue
import tempfile
import threading
from .config import BAUD, DEVICES
from .models import Record


def ports():
    try:
        from serial.tools import list_ports
        return [{"port": p.device, "description": p.description, "hwid": p.hwid} for p in list_ports.comports()]
    except ImportError:
        return []


def canonical(port):
    return port.upper().removeprefix("\\\\.\\") if os.name == "nt" else os.path.realpath(port)


class PortLock:
    def __init__(self, port):
        digest = hashlib.sha256(canonical(port).encode()).hexdigest()[:24]
        self.path = Path(tempfile.gettempdir()) / ("laser_guard_" + digest + ".lock")
        self.file = None

    def acquire(self):
        self.file = self.path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                self.file.write(b"0")
                self.file.flush()
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (OSError, IOError) as exc:
            self.file.close()
            self.file = None
            raise RuntimeError("다른 Dashboard 프로세스가 포트를 소유합니다") from exc

    def release(self):
        if self.file:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            self.file.close()
            self.file = None


class PortWorker:
    def __init__(self, device, port, receive, status, factory=None):
        self.device, self.port = device, port
        self.receive, self.status = receive, status
        self.factory = factory
        self.stop = threading.Event()
        self.queue = queue.Queue(maxsize=32)
        self.thread = threading.Thread(target=self.run, name=f"serial-{device}", daemon=True)
        self.connected = False
        self.lock = PortLock(port)

    def run(self):
        try:
            self.lock.acquire()
        except Exception as exc:
            self.status(self.device, False, self.port, str(exc))
            return
        try:
            while not self.stop.is_set():
                ser = None
                try:
                    if self.factory:
                        ser = self.factory(self.port)
                    else:
                        import serial
                        options = {"exclusive": True} if os.name != "nt" else {}
                        ser = serial.Serial(self.port, BAUD, timeout=.05, write_timeout=.5, **options)
                    self.connected = True
                    self.status(self.device, True, self.port)
                    pending = bytearray()
                    while not self.stop.is_set():
                        try:
                            task = self.queue.get_nowait()
                        except queue.Empty:
                            task = None
                        if task:
                            task(ser)  # CommandController owns validation immediately before write.
                        chunk = ser.read(min(getattr(ser, "in_waiting", 0) or 1, 4096))
                        for byte in chunk:
                            if byte in (10, 13):
                                if pending:
                                    self.receive(Record(self.device, self.port, pending.decode("utf-8", errors="replace")))
                                    pending.clear()
                            elif len(pending) < 8192:
                                pending.append(byte)
                            else:
                                raise ValueError("8192 bytes 초과: 줄바꿈 없는 스트림")
                except Exception as exc:
                    self.status(self.device, False, self.port, str(exc))
                finally:
                    self.connected = False
                    if ser:
                        ser.close()
                    while True:
                        try:
                            task = self.queue.get_nowait()
                        except queue.Empty:
                            break
                        task(None)  # Queued approvals are invalid across reconnects.
                self.stop.wait(1.0)
        finally:
            self.lock.release()
            self.status(self.device, False, self.port)

    def close(self):
        self.stop.set()
        self.thread.join(timeout=3)
        if self.thread.is_alive():
            raise RuntimeError("수신 스레드 종료 대기 중: 포트를 다시 열 수 없습니다")


class SerialManager:
    def __init__(self, receive, status, factory=None):
        self.receive, self.status, self.factory = receive, status, factory
        self.workers = {}
        self.lock = threading.RLock()

    def connect(self, device, port):
        with self.lock:
            if device not in DEVICES or not port.strip():
                raise ValueError("장치와 COM 포트를 선택하세요")
            if any(canonical(w.port) == canonical(port) for w in self.workers.values()):
                raise ValueError("이미 사용 중인 포트입니다")
            if device in self.workers:
                raise ValueError("기존 장치 연결을 먼저 해제하세요")
            worker = PortWorker(device, port, self.receive, self.status, self.factory)
            self.workers[device] = worker
            worker.thread.start()

    def disconnect(self, device):
        with self.lock:
            worker = self.workers.get(device)
        if worker:
            worker.close()
            with self.lock:
                self.workers.pop(device, None)

    def enqueue(self, device, task):
        with self.lock:
            worker = self.workers.get(device)
            if not worker or not worker.connected:
                raise ValueError("장치가 연결되지 않았습니다")
            worker.queue.put_nowait(task)

    def close(self):
        for device in list(self.workers):
            self.disconnect(device)
