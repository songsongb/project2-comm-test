"""Typed UI tables, bounded render caches and display-only transformations."""
from collections import OrderedDict
import json
import math
import pandas as pd
from .config import MODES
from .metrics import summarize


def text_cell(value):
    if value is None or value is pd.NA:
        return None
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(list(value) if isinstance(value, set) else value, ensure_ascii=False, default=str)
    return str(value)


def table(rows, numeric=(), boolean=(), columns=None):
    """Explicit Arrow dtypes, including legacy node=1/'window' and nested values."""
    frame = pd.DataFrame(rows, columns=columns)
    for name in frame:
        if name in numeric:
            frame[name] = pd.to_numeric(frame[name], errors="coerce").astype("Float64")
        elif name in boolean:
            frame[name] = frame[name].map(lambda v: v if isinstance(v, bool) else None).astype("boolean")
        else:
            frame[name] = frame[name].map(text_cell).astype("string")
    return frame


class RenderCache:
    def __init__(self, capacity=8):
        self.capacity = capacity
        self.items = OrderedDict()

    def get(self, key, factory):
        if key not in self.items:
            self.items[key] = factory()
        self.items.move_to_end(key)
        while len(self.items) > self.capacity:
            self.items.popitem(last=False)
        return self.items[key]


def comparison(rows, source=None, port=None, session=None):
    """Filter incompatible scopes BEFORE calling unchanged summarize()."""
    selected = [r for r in rows if (source is None or r["source"] == source) and
                (port is None or r["port"] == port) and (session is None or r["session"] == session)]
    summary = {(r["mode"], r["load"]): r for r in summarize(selected)}
    six = []
    for load in (0, 1):
        for mode, name in MODES.items():
            group = [r for r in selected if r["mode"] == mode and r["load"] == load]
            valid = summary.get((name, load))
            excluded = [r for r in group if not r["eligible"]]
            six.append({"mode": name, "load": load, "source": source or "No data", "port": port or "Unknown",
                        "session": session, "intervals": valid["intervals"] if valid else 0,
                        "samples_s": valid["samples_s"] if valid else None,
                        "observed_skip_pct": valid["observed_skip_pct"] if valid else None,
                        "irqs_s": valid["irqs_s"] if valid else None,
                        "acquisition_pct": valid["acquisition_pct"] if valid else None,
                        "acq_cycles": valid["acq_cycles"] if valid else None,
                        "cycles_s": valid["acq_cycles"] / valid["duration_s"] if valid else None,
                        "validity": "유효" if valid else "No data", "excluded": len(excluded),
                        "excluded_reason": "; ".join(sorted({r["excluded_reason"] or "Unknown" for r in excluded})),
                        "started_at": group[0]["received_at"] if group else None,
                        "ended_at": group[-1]["received_at"] if group else None})
    return six, selected


def extrema_points(rows, value, limit=400):
    """Display-only min/max buckets; retain all nulls and adjacent points.

    Null runs can exceed the soft limit. Never calculate statistics from this output.
    """
    if len(rows) <= limit:
        return rows
    step = max(1, math.ceil(len(rows) / max(1, limit // 4)))
    indices = {0, len(rows) - 1}
    for i, row in enumerate(rows):
        v = row.get(value)
        if v is None or (isinstance(v, float) and math.isnan(v)):
            indices.update((max(0, i - 1), i, min(len(rows) - 1, i + 1)))
    for start in range(0, len(rows), step):
        valid = [(i, rows[i].get(value)) for i in range(start, min(start + step, len(rows)))
                 if isinstance(rows[i].get(value), (int, float)) and math.isfinite(rows[i][value])]
        if valid:
            indices.update((valid[0][0], valid[-1][0], min(valid, key=lambda x: x[1])[0], max(valid, key=lambda x: x[1])[0]))
    return [rows[i] for i in sorted(indices)]
