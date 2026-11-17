"""JSONL raw-record replay preserves device, original PC time and provenance."""
import json
from datetime import datetime
import threading
from .config import DEVICES
from .models import Record


def read_jsonl(content):
    entries = []
    for number, line in enumerate(content.splitlines(), 1):
        if not line.strip():
            continue
        try:
            obj = json.loads(line)
            if obj["device"] not in DEVICES or not isinstance(obj["raw"], str):
                raise ValueError("device/raw 구조 오류")
            if obj.get("source") not in ("live", "demo", "synthetic", "replay-live", "replay-synthetic"):
                raise ValueError("source가 live/demo/synthetic/replay-live/replay-synthetic 중 하나여야 합니다")
            timestamp = datetime.fromisoformat(obj["received_at"])
            if timestamp.tzinfo is None:
                raise ValueError("PC 시각에 시간대가 필요합니다")
            entries.append(obj)
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError(f"JSONL {number}행: {exc}") from exc
    if not entries:
        raise ValueError("재생 로그가 비어 있습니다")
    return entries


def to_record(entry, demo=False):
    source = "demo" if demo else ("replay-live" if entry["source"] in ("live", "replay-live") else "replay-synthetic")
    return Record(entry["device"], entry.get("port", "replay"), entry["raw"],
                  source=source, received_at=entry["received_at"])


class Replay:
    def __init__(self, entries, receive, speed=1, demo=False):
        self.entries, self.receive, self.speed, self.demo = entries, receive, max(.1, speed), demo
        self.stop = threading.Event()
        self.position = 0
        self.error = None
        self.thread = threading.Thread(target=self.run, name="log-replay", daemon=True)

    def run(self):
        previous = None
        try:
            for i, entry in enumerate(self.entries):
                stamp = datetime.fromisoformat(entry["received_at"]).timestamp()
                if previous is not None and self.stop.wait(min(60, max(0, stamp - previous) / self.speed)):
                    break
                if self.stop.is_set():
                    break
                self.receive(to_record(entry, self.demo))
                self.position = i + 1
                previous = stamp
        except Exception as exc:
            self.error = str(exc)

    def start(self):
        self.thread.start()

    def close(self):
        self.stop.set()
        self.thread.join(timeout=2)
