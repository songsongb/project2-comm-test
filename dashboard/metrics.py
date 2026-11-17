"""Interval counts must never be differenced as cumulative counters."""
from dataclasses import dataclass, field, asdict
from .config import MODES, TARGET_HZ


class Metrics:
    def __init__(self):
        self.previous = {}
        self.condition_since = {}

    def reset_device(self, device):
        for key in list(self.previous):
            if key[0] == device:
                self.previous.pop(key)
                self.condition_since.pop(key, None)

    def add(self, record):
        d = record.data
        key = (record.device, record.port, record.source, record.session)
        prev = self.previous.get(key)
        condition = (d["mode"], d["load"])
        changed = prev is None or (prev.data["mode"], prev.data["load"]) != condition
        if changed:
            self.condition_since[key] = record.mcu_ms
        dt = ((record.mcu_ms - prev.mcu_ms) & 0xFFFFFFFF) if prev else None
        reason = None
        if prev is None:
            reason = "첫 STAT: 보고 길이 미확정"
        elif changed:
            reason = "MODE/LOAD 전환 구간"
        elif not 500 <= dt <= 1500:
            reason = "보고 간격 이상/누락: 펌웨어 구간 길이 미확정"
        elif ((record.mcu_ms - self.condition_since[key]) & 0xFFFFFFFF) <= 1000:
            reason = "전환 후 안정화 구간"
        self.previous[key] = record
        denom = d["pairs"] + d["skipped"]
        return {**d, "record_id": record.id, "session": record.session,
                "source": record.source, "port": record.port, "received_at": record.received_at,
                "ingested_at": record.ingested_at, "mode_name": MODES[d["mode"]],
                "duration_ms": dt, "eligible": reason is None and bool(d["ready"]),
                "excluded_reason": reason or (None if d["ready"] else "센서 미준비"),
                "samples_s": d["pairs"] * 1000 / dt if dt and not reason else None,
                "irqs_s": d["acq_irqs"] * 1000 / dt if dt and not reason else None,
                "observed_skip_pct": 100 * d["skipped"] / denom if denom else None,
                "acquisition_pct": d["acq_permille"] / 10}


def summarize(rows):
    groups = {}
    for row in rows:
        if row["eligible"]:
            key = (row["source"], row["mode"], row["load"])
            groups.setdefault(key, []).append(row)
    result = []
    for (source, mode, load), group in sorted(groups.items()):
        elapsed = sum(r["duration_ms"] for r in group)
        pairs = sum(r["pairs"] for r in group)
        skip = sum(r["skipped"] for r in group)
        result.append({"source": source, "mode": MODES[mode], "load": load,
                       "intervals": len(group), "duration_s": elapsed / 1000,
                       "pairs": pairs, "skipped": skip, "samples_s": pairs * 1000 / elapsed,
                       "observed_skip_pct": 100 * skip / (pairs + skip) if pairs + skip else None,
                       "irqs_s": sum(r["acq_irqs"] for r in group) * 1000 / elapsed,
                       "acq_cycles": sum(r["acq_cycles"] for r in group),
                       "acquisition_pct": sum(r["acquisition_pct"] * r["duration_ms"] for r in group) / elapsed,
                       "target_hz": TARGET_HZ})
    return result


@dataclass
class Experiment:
    id: str
    source: str
    started_at: str
    start_pc: float
    mode: int
    load: int
    session: int
    port: str
    warmup_s: float = 2
    ended_at: str | None = None
    rows: list = field(default_factory=list)

    def add(self, row):
        r = dict(row)
        if r["ingested_at"] - self.start_pc < self.warmup_s + (r["duration_ms"] or 0) / 1000:
            r.update(eligible=False, excluded_reason="실험 시작 안정화/경계 구간")
        if (r["mode"], r["load"], r["session"], r["port"]) != (self.mode, self.load, self.session, self.port):
            r.update(eligible=False, excluded_reason="실험 조건/세션 변경")
        self.rows.append(r)

    def as_dict(self):
        return {**asdict(self), "summary": summarize(self.rows),
                "excluded": sum(not r["eligible"] for r in self.rows)}
