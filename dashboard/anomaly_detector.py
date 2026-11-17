import uuid
from .models import utc_now

EVENTS = {"SENSOR_FAULT", "CAL_WAIT", "ARM_NOT_READY", "LINK_LOST", "CMD_TIMEOUT",
          "ARM_BUSY", "ARM_PATH_NOT_CLEAR", "CMD_REJECT", "CMD_BUSY_OR_ARMED"}


class AnomalyDetector:
    def __init__(self, cooldown=30):
        self.cooldown = cooldown
        self.last_alert = {}
        self.frame_errors = {}

    def check(self, record, metric=None):
        codes = []
        d = record.data
        if record.kind == "HUB":
            event = d["event"]
            if event in EVENTS or event.startswith("ALARM_"):
                codes.append(event)
            if event.endswith("FRAME_ERRORS"):
                key = (record.session, event)
                previous = self.frame_errors.get(key)
                if previous is not None and d["value"] > previous:
                    codes.append("FRAME_ERRORS_INCREASE")
                self.frame_errors[key] = d["value"]
        if record.kind == "STAT":
            if not d["ready"]:
                codes.append("WINDOW_NOT_READY")
            if d["skipped"]:
                codes.append("OBSERVED_SKIPS")
            if metric and metric["eligible"] and metric["samples_s"] < 9000:
                codes.append("DMA_THROUGHPUT_LOW" if d["mode"] == 2 else "THROUGHPUT_LOW")
            if d["mode"] == 2 and d["pairs"] == 0:
                codes.append("DMA_COLLECTION_STOPPED")
        if record.kind == "HALL" and d["fault"]:
            codes.append("DOOR_SENSOR_FAULT")
        if record.kind in ("TRACE_ABORT", "TRACE_ERROR"):
            codes.append(record.kind)
        if record.kind == "TRIAL":
            if not d["valid"]:
                codes.append("INVALID_TRIAL")
            elif not d["hit"]:
                codes.append("TRIAL_MISS")
        alerts = []
        for code in codes:
            node = d.get("node", record.device)
            key = (record.source, record.device, record.session, node, code)
            if record.ingested_at - self.last_alert.get(key, -float("inf")) < self.cooldown:
                continue
            self.last_alert[key] = record.ingested_at
            alerts.append({"id": uuid.uuid4().hex, "code": code, "device": record.device,
                           "node": node, "source": record.source, "session": record.session,
                           "received_at": record.received_at, "detected_at": utc_now(),
                           "status": "detected", "evidence_ids": [record.id],
                           "rule": "규칙 기반 관측; 하드웨어 원인 미확정"})
        return alerts
