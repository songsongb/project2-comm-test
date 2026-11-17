import pytest
from dashboard.models import Record
from dashboard.protocol_parser import parse, decode_flags
from dashboard.metrics import Metrics, summarize
from conftest import stat, event


def test_stat_exact_fields_and_types():
    r = stat()
    assert r.kind == "STAT" and len(r.data) == 17  # tag + 17 numeric fields
    assert all(type(v) is int for v in r.data.values())
    assert r.data["event_drops"] == 0 and r.data["acq_irqs"] == 312


@pytest.mark.parametrize("bad", ["STAT,1", "STAT,1,x", stat().raw + ",0", stat().raw.replace("9984", "1.5"), stat(mode=3).raw, stat(load=2).raw, stat(ready=2).raw, stat(pairs=-1).raw, stat(ms=2**32).raw])
def test_malformed_stat_rejected(bad):
    r = parse(Record("window", "COM12", bad))
    assert r.kind == "MALFORMED" and r.error


@pytest.mark.parametrize("mode,name", [(0, "Polling"), (1, "Interrupt"), (2, "DMA")])
def test_modes(mode, name):
    m = Metrics()
    row = m.add(stat(mode=mode))
    assert row["mode_name"] == name


def test_interval_throughput_not_counter_difference():
    m = Metrics()
    assert not m.add(stat(ms=2000))["eligible"]
    m.add(stat(ms=3000))  # conservative warmup
    row = m.add(stat(ms=4200, pairs=10800, skipped=1200, irqs=360))
    assert row["eligible"]
    assert row["samples_s"] == 9000
    assert row["observed_skip_pct"] == 10
    assert row["irqs_s"] == 300
    assert row["acquisition_pct"] == 10


def test_transition_gap_and_missing_logs_excluded():
    m = Metrics()
    m.add(stat(2000, mode=0))
    m.add(stat(3000, mode=0))
    assert m.add(stat(4000, mode=0))["eligible"]
    assert not m.add(stat(6000, mode=2))["eligible"]
    assert not m.add(stat(7000, mode=2))["eligible"]
    assert m.add(stat(8000, mode=2))["eligible"]
    assert not m.add(stat(11000, mode=2))["eligible"]
    assert m.add(stat(12000, mode=2))["eligible"]


def test_summary_weighted_and_load_separated():
    m = Metrics()
    m.add(stat(2000))
    m.add(stat(3000))
    a = m.add(stat(4000, pairs=10000, permille=100))
    b = m.add(stat(5200, pairs=12000, permille=200))
    m.add(stat(7000, load=1))
    m.add(stat(8000, load=1))
    c = m.add(stat(9000, load=1))
    rows = summarize([a, b, c])
    assert len(rows) == 2
    assert rows[0]["samples_s"] == 10000
    assert rows[0]["acquisition_pct"] == pytest.approx((10 * 1000 + 20 * 1200) / 2200)


def test_zero_denominator_unknown():
    assert Metrics().add(stat(pairs=0, skipped=0))["observed_skip_pct"] is None


def test_hub_alarm_and_status_alias_not_window_stat():
    r = event(name="ALARM_BEAM", node=1, value=600, state="ALARM")
    assert r.kind == "HUB" and r.data["state"] == "ALARM"
    assert parse(Record("hub", "COM11", "STAT,2000,2,0")).kind == "RAW"
    assert event(name="CMD_ACK", node=1, value=(0x80 << 8) | 2).data["command_type"] == 0x80


def test_flags():
    assert decode_flags(7) == {"READY": True, "ACTIVE": True, "SENSOR_FAULT": True, "unknown_bits": 0}
    assert decode_flags(8)["unknown_bits"] == 8


def test_door_and_uno_device_specific():
    r = parse(Record("door", "COM13", "1000,2000,2000,0,1,0,4,0"))
    assert r.kind == "HALL" and r.data["shock_edges"] == 4
    p = parse(Record("uno", "COM14", "pulse,1,151"))
    assert p.kind == "PULSE" and p.data["off_ms"] == 151
