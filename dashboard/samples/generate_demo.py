"""Reproducible SYNTHETIC fixtures; these values are not measured DMA results."""
import json
from pathlib import Path
from datetime import datetime, timedelta, timezone


def generate():
    base = datetime(2026, 1, 1, tzinfo=timezone.utc)
    rows = []
    def emit(ms, device, raw):
        rows.append({"received_at": (base + timedelta(milliseconds=ms)).isoformat(timespec="milliseconds"),
                     "source": "synthetic", "device": device, "port": "synthetic:" + device, "raw": raw})
    emit(0, "window", "A,10kHz,PA1 LDR,PA4 microphone,PB0 trial,TH 10-95,TRACE,PLOT/PLOTOFF")
    emit(0, "hub", "ms,event,node,value,state")
    emit(0, "door", "B,door,hall=PA0,shock=PA8")
    emit(0, "uno", "Laser Guard D ready. Enter HELP for commands.")
    for load in (0, 1):
        for mode in (0, 1, 2):
            phase = (load * 3 + mode) * 12000
            for second in range(2, 12):
                ms = phase + second * 1000
                pairs = 8400 if load and mode == 0 else 9984 if mode == 2 else 10000
                skipped = 10000 - pairs if mode != 2 else 0
                cycles = (13000000, 14000000, 6500000)[mode]
                irqs = (0, pairs, 312)[mode]
                emit(ms, "window", f"STAT,{ms},{mode},{load},10000,{pairs},{skipped},{cycles},{cycles * 1000 // 64000000},{irqs},3000,2900,3100,3000,1500,18,1,0")
                emit(ms, "door", f"{ms},2000,2000,0,1,0,0,0")
                for event, node, value in (("WINDOW_FLAGS", 1, 1), ("DOOR_FLAGS", 2, 1), ("WINDOW_MODE", 1, mode), ("WINDOW_FRAME_ERRORS", 1, 0), ("DOOR_FRAME_ERRORS", 2, 0)):
                    emit(ms, "hub", f"{ms},{event},{node},{value},DISARMED")
                for offset in range(0, 1000, 200):
                    emit(ms + offset, "window", f"PLOT,{ms + offset},{3000 + (second % 3) * 15}")
            emit(phase + 9000, "window", f"TRIAL,{phase + 8000},{mode},{load},150,1,1")
    emit(71500, "window", "TRIAL,71000,2,1,100,0,0")
    emit(71600, "hub", "71600,SENSOR_FAULT,1,4,FAULT")
    emit(71700, "window", "TRACE_BEGIN,10000,-1000,1000,2,1,1500")
    # Capture includes an explicit 4-slot gap, full 2001-slot coverage.
    t = 71703
    offset = -1000
    while offset <= 1000:
        if offset == -2:
            emit(t, "window", "TRACE_GAP,-2,4")
            offset += 4
        else:
            light = 3000 if offset < 0 or offset > 200 else 600
            emit(t, "window", f"TRACE_DATA,{offset},{light},2048")
            offset += 1
        t += 3
    emit(t, "window", "TRACE_END,1997,4")
    emit(t + 3, "window", "TRACE_ABORT,timeout")
    return sorted(rows, key=lambda r: r["received_at"])


if __name__ == "__main__":
    path = Path(__file__).with_name("synthetic_demo.jsonl")
    path.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in generate()) + "\n", encoding="utf-8")
    print(f"SYNTHETIC: {path.name}")
