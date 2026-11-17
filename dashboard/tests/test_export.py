import json
import pytest
from dashboard.export_logs import export
from conftest import stat


def test_export_all_raw_and_no_overwrite(tmp_path, storage):
    for ms in range(2000, 6000, 1000):
        storage.record(stat(ms))
    target = tmp_path / "all.jsonl"
    assert export(tmp_path / "test.sqlite3", target) == 4
    rows = [json.loads(line) for line in target.read_text().splitlines()]
    assert rows[0]["data"]["time_ms"] == 2000
    assert rows[0]["source"] == "live"
    with pytest.raises(FileExistsError):
        export(tmp_path / "test.sqlite3", target)
    with pytest.raises(ValueError):
        export(tmp_path / "test.sqlite3", tmp_path / "test.sqlite3")
