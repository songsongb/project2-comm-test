import json
import time
import pytest
from dashboard.models import Record
from dashboard.protocol_parser import parse
from dashboard.replay import read_jsonl, to_record
from conftest import stat, event, feed_status


def feed(state, raw):
    return state.ingest(parse(Record("window", "COM12", raw)))


def test_plot_and_mixed_devices(state):
    state.ingest(stat())
    state.ingest(event())
    feed(state, "PLOT,2100,3020")
    snap = state.snapshot()
    assert snap["plots"][-1]["ldr"] == 3020
    assert snap["devices"]["window"]["latest"]["port"] == "COM12"
    assert snap["devices"]["hub"]["latest"]["port"] == "COM11"
    assert len(snap["metrics"]) == 1


def test_reboot_wrap_and_delayed_trial(state):
    state.ingest(stat(2000))
    feed(state, "PLOT,2500,3000")
    feed(state, "TRIAL,1000,2,0,150,1,1")
    assert state.sessions["window"] == 0
    state.ingest(stat(100))
    assert state.sessions["window"] == 1
    assert not state.metric_rows[-1]["eligible"]
    state.ingest(stat(0xFFFFFF00))
    state.ingest(stat(100))
    assert state.sessions["window"] == 1  # 32-bit millis wrap


def test_boot_without_clock_resets_hub_status(state):
    feed_status(state)
    assert state.status
    state.ingest(parse(Record("hub", "COM11", "ms,event,node,value,state")))
    assert state.status is None and state.sessions["hub"] == 1


def test_trace_gaps_and_pc_missing_rows(state):
    feed(state, "TRACE_BEGIN,10000,-2,2,2,0,1500")
    feed(state, "TRACE_DATA,-2,3000,2048")
    feed(state, "TRACE_GAP,-1,2")
    feed(state, "TRACE_DATA,1,600,2048")
    feed(state, "TRACE_DATA,2,600,2048")
    feed(state, "TRACE_END,3,2")
    trace = state.snapshot()["traces"][-1]
    assert trace["status"] == "complete"
    assert trace["rows"][1]["ldr"] is None and trace["rows"][2]["gap"]
    feed(state, "TRACE_BEGIN,10000,-1,1,2,0,1500")
    feed(state, "TRACE_DATA,-1,3000,2048")
    feed(state, "TRACE_DATA,1,600,2048")
    feed(state, "TRACE_END,3,0")
    trace = state.snapshot()["traces"][-1]
    assert trace["status"] == "incomplete" and trace["rows"][1]["ldr"] is None


def test_trace_abort(state):
    feed(state, "TRACE_BEGIN,10000,-1,1,2,0,1500")
    feed(state, "TRACE_ABORT,configuration_changed")
    assert state.snapshot()["traces"][-1]["status"] == "aborted"


def test_trial_validity_and_stale_data(state):
    feed(state, "TRIAL,100,2,0,150,1,1")
    feed(state, "TRIAL,1000,2,0,0,1,0")
    assert sum(t["valid"] for t in state.trials) == 1
    state.ingest(stat(2000, ingested_at=10))
    assert state.snapshot(now=20)["devices"]["window"]["latest"] is None


def test_disconnect_immediately_hides_previous_current_status(state):
    state.ingest(stat())
    feed_status(state)
    state.set_connection("window", False, "COM12")
    state.set_connection("hub", False, "COM11")
    snap = state.snapshot()
    assert snap["hub_state"] == "Unknown"
    assert snap["devices"]["window"]["latest"] is None
    assert not snap["devices"]["window"]["fresh"]


def test_replay_live_consistency(state, storage):
    original = stat()
    state.ingest(original)
    obj = {"device": original.device, "port": original.port, "received_at": original.received_at,
           "source": "live", "raw": original.raw}
    replayed = parse(to_record(read_jsonl(json.dumps(obj))[0]))
    assert replayed.data == original.data
    assert replayed.source == "replay-live"
    assert replayed.received_at == original.received_at
    assert storage.raw_records()[0]["raw"] == original.raw


@pytest.mark.parametrize("obj", [{"raw": "x"}, {"device": "window", "raw": "x", "source": "live", "received_at": "2026-01-01"}])
def test_replay_bad_metadata_rejected(obj):
    with pytest.raises(ValueError):
        read_jsonl(json.dumps(obj))


def test_experiment_persistence_condition_change(state, storage):
    state.ingest(stat(2000))
    state.start_experiment("live", 0)
    state.experiment.start_pc -= 10
    state.ingest(stat(3000))
    state.ingest(stat(4000))
    state.ingest(stat(6000, mode=0))
    state.stop_experiment()
    exp = storage.history("experiment")[0]
    assert exp["started_at"] and exp["ended_at"]
    assert len(exp["rows"]) == 3 and exp["excluded"] == 2
    assert exp["summary"][0]["mode"] == "DMA"
