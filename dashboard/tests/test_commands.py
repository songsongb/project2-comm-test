import pytest
from conftest import stat, event, feed_status
from dashboard.command_controller import CommandController


class Wire:
    def __init__(self):
        self.writes = []

    def write(self, data):
        self.writes.append(data)
        return len(data)


class Serial:
    def __init__(self):
        self.tasks = []
        self.wire = Wire()

    def enqueue(self, device, task):
        assert device == "hub"
        self.tasks.append(task)

    def drain(self):
        for task in self.tasks:
            task(self.wire)
        self.tasks.clear()


@pytest.fixture
def rig(state, storage):
    now = [100.0]
    state.set_connection("hub", True, "COM11")
    feed_status(state, at=now[0])
    serial = Serial()
    controller = CommandController(state, serial, storage, clock=lambda: now[0])
    return controller, serial, now


def test_no_approval_and_forbidden_commands(rig):
    c, serial, _ = rig
    for command in ("ARM", "DISARM", "LASER ON", "TEST 150 1", "MODE 3", "MODE 2\r\nARM", "RESET"):
        assert not c.check(command)[0]
        with pytest.raises(ValueError):
            c.propose(command, True)
    p = c.propose("MODE 2", True)
    with pytest.raises(ValueError):
        c.approve(p["id"])
    assert not serial.tasks


def test_stale_missing_and_cal_baseline(rig, state):
    c, _, now = rig
    assert not c.check("CAL", idle_confirmed=True)[0]
    assert c.check("CAL", idle_confirmed=True, baseline_confirmed=True)[0]
    now[0] += 3
    assert not c.check("MODE 2", idle_confirmed=True)[0]
    state.status = None
    assert not c.check("MODE 2", idle_confirmed=True)[0]


def test_state_change_after_approval_blocks_at_actual_write(rig, state):
    c, serial, now = rig
    p = c.propose("MODE 2", True)
    c.approve(p["id"], True)
    state.ingest(event(2100, state="ARMED", ingested_at=now[0]))
    serial.drain()
    assert not serial.wire.writes
    assert c.current["status"] == "blocked"


def test_state_change_then_restore_still_invalidates(rig, state):
    c, serial, now = rig
    p = c.propose("MODE 2", True)
    c.approve(p["id"], True)
    state.ingest(event(2100, state="ARMED", ingested_at=now[0]))
    state.ingest(event(2200, state="DISARMED", ingested_at=now[0]))
    serial.drain()
    assert not serial.wire.writes


def test_duplicate_approval_and_multiple_proposals(rig):
    c, serial, _ = rig
    p = c.propose("MODE 2", True)
    p2 = c.propose("LOAD 1", True)
    c.approve(p["id"], True)
    with pytest.raises(ValueError):
        c.approve(p["id"], True)
    with pytest.raises(ValueError):
        c.approve(p2["id"], True)
    serial.drain()
    assert serial.wire.writes == [b"MODE 2\r\n"]


@pytest.mark.parametrize("outcome,status", [("CMD_REJECT", "failed"), ("CMD_TIMEOUT", "failed"), ("CMD_ACK", "awaiting_verification")])
def test_ack_reject_timeout(rig, state, outcome, status):
    c, serial, now = rig
    p = c.propose("MODE 2", True)
    c.approve(p["id"], True)
    serial.drain()
    now[0] += .1
    r = state.ingest(event(2100, outcome, 1, 0x8002, ingested_at=now[0]))
    c.on_record(r)
    assert c.current["status"] == status
    assert c.current["status"] != "verified"


def test_followup_status_and_actual_sensor_required(rig, state):
    c, serial, now = rig
    p = c.propose("MODE 2", True)
    c.approve(p["id"], True)
    serial.drain()
    now[0] += .1
    c.on_record(state.ingest(event(2100, "CMD_ACK", 1, 0x8002, ingested_at=now[0])))
    now[0] += 1
    feed_status(state, 3100, at=now[0])
    c.on_record(event(3100, ingested_at=now[0]))
    assert c.current["status"] == "awaiting_verification"
    r = state.ingest(stat(3100, ingested_at=now[0]))
    c.on_record(r)
    assert c.current["status"] == "verified" and "별도 관측" in c.current["result"]


def test_missing_ack_unknown_and_no_repeat(rig):
    c, serial, now = rig
    p = c.propose("MODE 2", True)
    c.approve(p["id"], True)
    serial.drain()
    now[0] += 13
    c.tick()
    assert c.current["status"] == "unknown"
    assert serial.wire.writes == [b"MODE 2\r\n"]


def test_reconnect_and_expired_queue_rejected(rig, state):
    c, serial, now = rig
    p = c.propose("LOAD 1", True)
    c.approve(p["id"], True)
    state.set_connection("hub", False, "COM11")
    state.set_connection("hub", True, "COM11")
    feed_status(state, at=now[0])
    serial.drain()
    assert not serial.wire.writes


def test_ack_wrong_node_or_value_ignored(rig, state):
    c, serial, now = rig
    p = c.propose("MODE 2", True)
    c.approve(p["id"], True)
    serial.drain()
    for node, value in ((2, 0x8002), (1, 0x8001)):
        c.on_record(state.ingest(event(2100, "CMD_ACK", node, value, ingested_at=now[0])))
    assert c.current["status"] == "sent"


def test_readonly_rate_limit(rig):
    c, serial, now = rig
    assert c.query()
    assert not c.query()
    now[0] += 1
    assert c.query("HELP")
    assert not c.query("ARM")
    serial.drain()
    assert serial.wire.writes == [b"STATUS\r\n", b"HELP\r\n"]


def test_cal_requires_both_acks_and_both_sensor_followups(rig, state):
    from dashboard.protocol_parser import parse
    from dashboard.models import Record
    c, serial, now = rig
    p = c.propose("CAL", True, True)
    c.approve(p["id"], True)
    serial.drain()
    now[0] += .1
    c.on_record(state.ingest(event(2100, "CMD_ACK", 1, 0x8200, ingested_at=now[0])))
    assert c.current["status"] == "sent"
    c.on_record(state.ingest(event(2100, "CMD_ACK", 2, 0x8200, ingested_at=now[0])))
    assert c.current["status"] == "awaiting_verification"
    now[0] += 2
    feed_status(state, 4100, at=now[0])
    c.on_record(state.ingest(stat(4100, ingested_at=now[0])))
    assert c.current["status"] == "awaiting_verification"
    door = parse(Record("door", "COM13", "4100,2000,2000,0,1,0,0,0", ingested_at=now[0]))
    c.on_record(state.ingest(door))
    assert c.current["status"] == "verified"


def test_stale_at_write_and_expired_approval(rig):
    c, serial, now = rig
    p = c.propose("MODE 2", True)
    c.approve(p["id"], True)
    now[0] += 3
    serial.drain()
    assert not serial.wire.writes and c.current["status"] == "blocked"


def test_replay_status_never_authorizes_hardware(rig, state):
    c, _, _ = rig
    state.status["source"] = "replay-live"
    assert not c.check("MODE 2", idle_confirmed=True)[0]


def test_pending_external_command_rejects_proposal(rig, state):
    c, _, now = rig
    state.ingest(event(2050, "CMD", 1, 0x8301, ingested_at=now[0]))
    assert not c.check("MODE 2", idle_confirmed=True)[0]


def test_partial_write_is_uncertain_and_not_retried(rig):
    c, serial, _ = rig
    serial.wire.write = lambda data: len(data) - 1
    p = c.propose("MODE 2", True)
    c.approve(p["id"], True)
    serial.drain()
    assert c.current["status"] == "unknown"


def test_proposal_ttl_expires_even_with_new_fresh_status(rig, state, storage):
    c, serial, now = rig
    p = c.propose("MODE 2", True)
    now[0] += 21
    feed_status(state, ms=23000, at=now[0])
    with pytest.raises(ValueError, match="승인 만료"):
        c.approve(p["id"], True)
    assert not serial.tasks
    saved = next(item for item in storage.history("command") if item["id"] == p["id"])
    assert saved["status"] == "blocked" and saved["approved"]


def test_reset_after_ack_cannot_be_reported_as_recovery(rig, state):
    from dashboard.models import Record
    from dashboard.protocol_parser import parse
    c, serial, now = rig
    p = c.propose("MODE 2", True)
    c.approve(p["id"], True)
    serial.drain()
    now[0] += .1
    c.on_record(state.ingest(event(2100, "CMD_ACK", 1, 0x8002, ingested_at=now[0])))
    now[0] += .1
    boot = parse(Record("hub", "COM11", "ms,event,node,value,state", ingested_at=now[0]))
    c.on_record(state.ingest(boot))
    assert c.current["status"] == "unknown"
