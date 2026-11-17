from pathlib import Path
import sys
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dashboard.models import Record
from dashboard.protocol_parser import parse
from dashboard.storage import Storage
from dashboard.state_manager import StateManager


def stat(ms=2000, mode=2, load=0, pairs=9984, skipped=0, cycles=6400000, permille=100, irqs=312, ready=1, **kwargs):
    raw = f"STAT,{ms},{mode},{load},10000,{pairs},{skipped},{cycles},{permille},{irqs},3000,2900,3100,3000,1500,18,{ready},0"
    return parse(Record("window", "COM12", raw, **kwargs))


def event(ms=2000, name="STATE", node=3, value=0, state="DISARMED", **kwargs):
    return parse(Record("hub", "COM11", f"{ms},{name},{node},{value},{state}", **kwargs))


def feed_status(state, ms=2000, mode=2, flags=1, at=None):
    import time
    at = time.time() if at is None else at
    for name, node, value in (("WINDOW_FLAGS", 1, flags), ("DOOR_FLAGS", 2, 1), ("WINDOW_MODE", 1, mode), ("WINDOW_FRAME_ERRORS", 1, 0), ("DOOR_FRAME_ERRORS", 2, 0)):
        state.ingest(event(ms, name, node, value, ingested_at=at))


@pytest.fixture
def storage(tmp_path):
    store = Storage(tmp_path / "test.sqlite3")
    yield store
    store.close()


@pytest.fixture
def state(storage):
    manager = StateManager(storage)
    manager.set_connection("window", True, "COM12")
    manager.set_connection("hub", True, "COM11")
    return manager
