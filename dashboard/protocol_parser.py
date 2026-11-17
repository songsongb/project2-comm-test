"""Parsers for the six supplied source files, NOT the smoke-test protocol."""
import re
from .models import Record
from .config import DEVICES

STAT_FIELDS = "time_ms mode load slots pairs skipped acq_cycles acq_permille acq_irqs ldr min max lit_baseline ldr_threshold mic_rms ready event_drops".split()
STATES = {"DISARMED", "ARMED", "SUSPECT", "ALARM", "FAULT"}


class ParseError(ValueError):
    pass


def integer(value, low=0, high=0xFFFFFFFF):
    if not re.fullmatch(r"-?[0-9]+", value):
        raise ParseError(f"정수가 아닙니다: {value!r}")
    result = int(value)
    if not low <= result <= high:
        raise ParseError(f"범위 밖 정수: {result}")
    return result


def numbers(parts, fields, signed=()):
    if len(parts) != len(fields):
        raise ParseError(f"필드 수 {len(parts)}: {len(fields)}개 필요")
    return {k: integer(v, -1000000 if k in signed else 0) for k, v in zip(fields, parts)}


def require(data, field, low, high):
    if not low <= data[field] <= high:
        raise ParseError(f"{field} 범위 오류")


def decode_flags(value):
    return {"READY": bool(value & 1), "ACTIVE": bool(value & 2),
            "SENSOR_FAULT": bool(value & 4), "unknown_bits": value & ~7}


def window(parts):
    tag = parts[0]
    if tag == "STAT":
        data = numbers(parts[1:], STAT_FIELDS)
        require(data, "mode", 0, 2)
        for k in ("load", "ready"):
            require(data, k, 0, 1)
        require(data, "slots", 0, 65535)
        for k in ("ldr", "min", "max", "lit_baseline", "ldr_threshold"):
            require(data, k, 0, 4095)
        require(data, "mic_rms", 0, 65535)
        return tag, data["time_ms"], data
    formats = {
        "PLOT": "time_ms ldr", "TRIAL": "start_ms mode load command_ms hit valid",
        "TRACE_BEGIN": "sample_hz first last mode load threshold",
        "TRACE_DATA": "offset ldr mic", "TRACE_GAP": "offset count",
        "TRACE_END": "valid missing", "TRACE_WAIT": "pre_ms", "TH": "percent",
    }
    if tag in formats:
        data = numbers(parts[1:], formats[tag].split(), ("first", "last", "offset"))
        for k, high in (("mode", 2), ("load", 1), ("hit", 1), ("valid", 1 if tag == "TRIAL" else 0xFFFFFFFF), ("ldr", 4095), ("mic", 4095)):
            if k in data:
                require(data, k, 0, high)
        if tag == "TRACE_BEGIN":
            require(data, "sample_hz", 1, 1000000)
            require(data, "first", -1000, 1000)
            require(data, "last", data["first"], 1000)
        if tag == "TRACE_GAP":
            require(data, "count", 1, 64)
        if tag == "TRACE_DATA" or tag == "TRACE_GAP":
            require(data, "offset", -1000, 1000)
        return tag, data.get("time_ms"), data  # TRIAL time is delayed, not a reboot clock.
    if tag in ("TRACE_ABORT", "TRACE_ERROR"):
        if len(parts) != 2 or not parts[1]:
            raise ParseError("TRACE 사유 누락")
        return tag, None, {"reason": parts[1]}
    if tag in ("TRACE_ARMED", "PLOT_OFF") and len(parts) == 1:
        return tag, None, {}
    return "RAW", None, {}


def door(parts):
    if not parts[0].isdigit():
        return "RAW", None, {}
    data = numbers(parts, "time_ms raw closed delta ready open shock_edges fault".split())
    for k in ("raw", "closed", "delta"):
        require(data, k, 0, 4095)
    for k in ("ready", "open", "fault"):
        require(data, k, 0, 1)
    return "HALL", data["time_ms"], data


def hub(parts):
    if not parts[0].isdigit():
        return "RAW", None, {}
    if len(parts) != 5 or parts[4] not in STATES or not re.fullmatch("[A-Z_]+", parts[1]):
        raise ParseError("허브 이벤트 구조 오류")
    data = {"event": parts[1], "node": integer(parts[2], 1, 3),
            "value": integer(parts[3]), "state": parts[4]}
    if data["event"] in ("WINDOW_FLAGS", "DOOR_FLAGS", "READY", "SENSOR_FAULT", "CAL_WAIT", "LINK_LOST"):
        data["flags"] = decode_flags(data["value"])
    if data["event"] in ("CMD", "CMD_ACK", "CMD_REJECT", "CMD_TIMEOUT"):
        data.update(command_type=data["value"] >> 8, command_value=data["value"] & 255)
    return "HUB", integer(parts[0]), data


def uno(parts):
    if parts[0] == "pulse":
        return "PULSE", None, numbers(parts[1:], ["number", "off_ms"])
    if len(parts) == 1 and parts[0] in {"TEST_STARTED", "TEST_ABORTED", "TEST_DONE", "LASER_ON", "LASER_OFF", "BUSY_OR_HUB_NOT_NORMAL", "COMMAND_TOO_LONG"}:
        return "UNO_EVENT", None, {"event": parts[0]}
    return "RAW", None, {}


PARSERS = dict(window=window, door=door, hub=hub, uno=uno)


def parse(record: Record):
    if record.device not in DEVICES:
        raise ValueError("장치 매핑이 필요합니다")
    parts = record.raw.strip().split(",")
    headers = ((parts[0] == "STAT" and len(parts) > 1 and parts[1] == "time_ms") or
               (parts[0] == "TRIAL" and len(parts) > 1 and parts[1] == "start_ms") or
               parts[0] == "ms")
    boot = ((record.device == "window" and record.raw.startswith("A,10kHz,")) or
            (record.device == "door" and record.raw.startswith("B,door,")) or
            (record.device == "hub" and record.raw.strip() == "ms,event,node,value,state") or
            (record.device == "uno" and record.raw.startswith("Laser Guard D ready.")))
    try:
        if boot:
            record.kind = "BOOT"
        elif headers:
            record.kind = "HEADER"
        else:
            record.kind, record.mcu_ms, record.data = PARSERS[record.device](parts)
    except (ParseError, ValueError) as exc:
        record.kind, record.error = "MALFORMED", str(exc)
    return record
