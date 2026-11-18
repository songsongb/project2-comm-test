from collections import deque
from copy import deepcopy
import threading
import time
import uuid
from .config import DEVICES, FRESH_SECONDS
from .metrics import Metrics, Experiment
from .models import utc_now


class TraceCapture:
    def __init__(self, record):
        self.id = record.id
        self.source, self.session, self.port = record.source, record.session, record.port
        self.received_at = record.received_at
        self.meta = dict(record.data)
        self.points = {}
        self.gaps = []
        self.status = "capturing"
        self.reason = None

    def feed(self, record):
        d = record.data
        if record.kind in ("TRACE_DATA", "TRACE_GAP"):
            offsets = range(d["offset"], d["offset"] + (d["count"] if record.kind == "TRACE_GAP" else 1))
            for offset in offsets:
                if offset < self.meta["first"] or offset > self.meta["last"] or offset in self.points:
                    self.reason = "중복/범위 오류 행"
                    continue
                self.points[offset] = (d["ldr"], d["mic"]) if record.kind == "TRACE_DATA" else (None, None)
            if record.kind == "TRACE_GAP":
                self.gaps.append((d["offset"], d["count"]))
        elif record.kind == "TRACE_END":
            valid = sum(v[0] is not None for v in self.points.values())
            missing = sum(v[0] is None for v in self.points.values())
            count = self.meta["last"] - self.meta["first"] + 1
            ok = len(self.points) == count and valid == d["valid"] and missing == d["missing"] and self.reason is None
            self.status = "complete" if ok else "incomplete"
            if not ok:
                self.reason = "TRACE_END 개수 불일치 또는 PC 수신 누락"
        elif record.kind == "TRACE_ABORT":
            self.status, self.reason = "aborted", d["reason"]

    def as_dict(self):
        # Every absent slot is an explicit null. Plotly connectgaps=False is required.
        return {"id": self.id, "source": self.source, "session": self.session, "port": self.port,
                "received_at": self.received_at, "meta": self.meta, "status": self.status,
                "reason": self.reason, "gaps": self.gaps,
                "rows": [{"offset": i, "time_ms": i * 1000 / self.meta["sample_hz"],
                          "ldr": self.points.get(i, (None, None))[0],
                          "mic": self.points.get(i, (None, None))[1],
                          "gap": self.points.get(i, (None, None))[0] is None}
                         for i in range(self.meta["first"], self.meta["last"] + 1)]}


class StateManager:
    def __init__(self, storage):
        self.storage = storage
        self.identity = uuid.uuid4().hex
        self.lock = threading.RLock()
        self.metrics = Metrics()
        self.sessions = {d: 0 for d in DEVICES}
        self.clocks = {}
        self.last = {}
        self.latest = {}
        self.hub_state = None
        self.status_parts = {}
        self.status = None
        self.experiment_active = None
        self.safety_epoch = 0
        self.pending_nodes = set()
        self.records = deque(maxlen=2000)
        self.metric_rows = deque(maxlen=7200)
        self.plots = deque(maxlen=3000)
        self.trials = deque(maxlen=1000)
        self.events = deque(maxlen=500)
        self.security_events = deque(maxlen=120)
        self.node_health = {}
        self.uno_event = None
        self.revisions = {k: 0 for k in ("metrics", "sensors", "events", "records")}
        self.traces = deque(maxlen=15)
        self.active_trace = None
        self.trace_status = None
        self.experiment = None
        self.connection = {d: {"connected": False, "port": None, "error": None} for d in DEVICES}

    def set_connection(self, device, connected, port, error=None):
        with self.lock:
            if self.connection[device]["connected"] != connected or self.connection[device]["port"] != port:
                self.safety_epoch += 1
            self.connection[device] = {"connected": connected, "port": port, "error": error}
            if not connected:
                self.latest.pop(device, None)
                if device == "hub":
                    self.status = None
                    self.hub_state = None

    def _new_session(self, device):
        self.safety_epoch += 1
        self.sessions[device] += 1
        self.clocks.pop(device, None)
        self.metrics.reset_device(device)
        self.latest.pop(device, None)
        if device == "hub":
            self.status, self.hub_state, self.experiment_active = None, None, None
            self.status_parts.clear()
            self.pending_nodes.clear()
            self.node_health.clear()
        if device == "window" and self.active_trace:
            self.active_trace.status, self.active_trace.reason = "aborted", "device_restart"
            self.storage.save("trace", self.active_trace.as_dict())
            self.active_trace = None

    def ingest(self, record):
        with self.lock:
            prev_clock = self.clocks.get(record.device)
            reset = (record.mcu_ms is not None and prev_clock is not None and
                     record.mcu_ms < prev_clock and not (prev_clock > 0xF0000000 and record.mcu_ms < 0x0FFFFFFF))
            if (record.kind == "BOOT" and record.device in self.last) or reset:
                self._new_session(record.device)
            record.session = self.sessions[record.device]
            if record.mcu_ms is not None:
                self.clocks[record.device] = record.mcu_ms
            self.last[record.device] = record
            self.records.append(record)
            self.revisions["records"] += 1
            if record.kind in ("STAT", "HALL", "HUB"):
                self.latest[record.device] = record
            if record.kind == "STAT":
                self.revisions["metrics"] += 1
                row = self.metrics.add(record)
                self.metric_rows.append(row)
                if self.experiment:
                    self.experiment.add(row)
                    if len(self.experiment.rows) >= 7200:
                        self.stop_experiment()  # Bound RAM; raw data continue in SQLite.
            elif record.kind == "PLOT":
                self.plots.append({**record.data, "source": record.source, "session": record.session,
                                   "received_at": record.received_at})
            elif record.kind == "TRIAL":
                self.trials.append({**record.data, "source": record.source, "session": record.session,
                                    "received_at": record.received_at})
            elif record.kind == "HUB":
                self._hub(record)
                self.events.append(record.as_dict())
                if record.data["event"] not in {"WINDOW_FLAGS", "DOOR_FLAGS", "WINDOW_MODE", "WINDOW_FRAME_ERRORS", "DOOR_FRAME_ERRORS"}:
                    self.security_events.append(record.as_dict())
                    self.revisions["events"] += 1
            elif record.kind == "UNO_EVENT":
                self.uno_event = record.as_dict()
            if record.kind in ("PLOT", "TRIAL") or record.kind.startswith("TRACE_"):
                self.revisions["sensors"] += 1
            if record.kind == "TRACE_BEGIN":
                if self.active_trace:
                    self.active_trace.status, self.active_trace.reason = "incomplete", "새 BEGIN으로 중단"
                    self.storage.save("trace", self.active_trace.as_dict())
                self.active_trace = TraceCapture(record)
                self.traces.append(self.active_trace)
            elif record.kind.startswith("TRACE_") and self.active_trace:
                self.active_trace.feed(record)
                if self.active_trace.status != "capturing":
                    self.storage.save("trace", self.active_trace.as_dict())
                    self.active_trace = None
            if record.kind.startswith("TRACE_"):
                self.trace_status = {"kind": record.kind, "source": record.source,
                                     "received_at": record.received_at, **record.data}
            self.storage.record(record)
            return record

    def _hub(self, r):
        d = r.data
        if self.hub_state and self.hub_state["state"] != d["state"]:
            self.safety_epoch += 1
        self.hub_state = {"state": d["state"], "at": r.ingested_at, "source": r.source}
        event = d["event"]
        if event in {"READY", "LINK_LOST", "CAL_WAIT", "SENSOR_FAULT", "LINK_STARTING"}:
            self.node_health[str(d["node"])] = {"event": event, "at": r.ingested_at, "received_at": r.received_at}
        if event == "CMD":
            self.pending_nodes.add(d["node"])
            self.safety_epoch += 1
        elif event in ("CMD_ACK", "CMD_REJECT", "CMD_TIMEOUT"):
            self.pending_nodes.discard(d["node"])
        if event in ("TEST_STARTED", "TEST_STARTED_ARMED"):
            self.safety_epoch += 1
            self.experiment_active = True
        elif event == "TEST_ENDED":
            self.safety_epoch += 1
            self.experiment_active = False
        keys = {"WINDOW_FLAGS", "DOOR_FLAGS", "WINDOW_MODE", "WINDOW_FRAME_ERRORS", "DOOR_FRAME_ERRORS"}
        if event in keys:
            if self.status and self.status.get(event) != d["value"] and not event.endswith("FRAME_ERRORS"):
                self.safety_epoch += 1
            group = self.status_parts.setdefault(r.mcu_ms, {})
            group[event] = d["value"]
            if keys <= group.keys():
                self.status = {**group, "state": d["state"], "at": r.ingested_at,
                               "mcu_ms": r.mcu_ms, "session": r.session, "source": r.source}
            self.status_parts = {k: v for k, v in self.status_parts.items() if k == r.mcu_ms}

    def start_experiment(self, source, warmup_s=2):
        with self.lock:
            if self.experiment:
                raise ValueError("진행 중인 실험을 먼저 종료하세요")
            r = self.latest.get("window")
            if not r or time.time() - r.ingested_at > FRESH_SECONDS:
                raise ValueError("최신 Window STAT가 필요합니다")
            self.experiment = Experiment(uuid.uuid4().hex, source, utc_now(), time.time(),
                                         r.data["mode"], r.data["load"], r.session, r.port, warmup_s)

    def stop_experiment(self):
        with self.lock:
            if self.experiment:
                self.experiment.ended_at = utc_now()
                self.storage.save("experiment", self.experiment.as_dict())
                self.experiment = None

    def snapshot(self, now=None, view="all", details=False):
        now = time.time() if now is None else now
        with self.lock:
            devices = {}
            for device in DEVICES:
                r = self.last.get(device)
                latest = self.latest.get(device)
                fresh = r is not None and now - r.ingested_at <= FRESH_SECONDS
                if r and r.source == "live" and not self.connection[device]["connected"]:
                    fresh = False
                devices[device] = {**self.connection[device], "fresh": fresh,
                                   "last_received": r.received_at if r else None,
                                   "age_s": now - r.ingested_at if r else None,
                                   "session": self.sessions[device],
                                   "latest": latest.as_dict() if latest and now - latest.ingested_at <= FRESH_SECONDS and (latest.source != "live" or self.connection[device]["connected"]) else None}
            state = self.hub_state["state"] if self.hub_state and devices["hub"]["fresh"] and now - self.hub_state["at"] <= FRESH_SECONDS else "Unknown"
            if view != "all":
                # Metric/plot rows are immutable after ingest. Copy their references
                # instead of deep-copying every retained record under the reader lock.
                result = deepcopy({"devices": devices, "hub_state": state, "status": self.status,
                                   "node_health": self.node_health, "uno_event": self.uno_event,
                                   "revisions": self.revisions, "events": list(self.security_events),
                                   "experiment": None if not self.experiment else {
                                       k: getattr(self.experiment, k) for k in ("id", "source", "started_at", "mode", "load", "port", "session")}})
                result["records"] = []
                if view == "dma":
                    result["metrics"] = list(self.metric_rows)
                if details:
                    result.update(plots=list(self.plots)[-600:], trials=list(self.trials),
                                  traces=[t.as_dict() for t in self.traces], trace_status=deepcopy(self.trace_status))
                return result
            return deepcopy({"devices": devices, "hub_state": state, "status": self.status,
                             "metrics": list(self.metric_rows), "plots": list(self.plots),
                             "trials": list(self.trials), "events": list(self.events),
                             "traces": [t.as_dict() for t in self.traces],
                             "trace_status": self.trace_status,
                             "records": [r.as_dict() for r in self.records],
                             "experiment": self.experiment.as_dict() if self.experiment else None})

    def control_context(self):
        with self.lock:
            return deepcopy({"status": self.status, "hub_state": self.hub_state,
                             "safety_epoch": self.safety_epoch, "pending_nodes": sorted(self.pending_nodes),
                             "experiment_active": self.experiment_active,
                             "connected": self.connection["hub"]["connected"],
                             "window": self.latest.get("window").as_dict() if self.latest.get("window") else None,
                             "door": self.latest.get("door").as_dict() if self.latest.get("door") else None})
