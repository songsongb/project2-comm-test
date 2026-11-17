from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
import time
import uuid


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


@dataclass
class Record:
    device: str
    port: str
    raw: str
    source: str = "live"
    received_at: str = field(default_factory=utc_now)
    ingested_at: float = field(default_factory=time.time)
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    session: int = 0
    kind: str = "RAW"
    mcu_ms: int | None = None
    data: dict = field(default_factory=dict)
    error: str | None = None

    def as_dict(self):
        return asdict(self)
