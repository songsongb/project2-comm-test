#!/usr/bin/env python3
"""Read STM32 key=value logs without changing counters or fabricating data."""
import argparse
import queue
import sys
import threading
import time
from pathlib import Path

COMMANDS = {"ARM", "DISARM", "STATUS", "HELP"}


def normalized_command(text):
    command = text.strip().upper()
    if command not in COMMANDS:
        raise ValueError("Commands: ARM, DISARM, STATUS, HELP")
    return command


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", help="ST-LINK VCP, e.g. /dev/serial/by-id/...")
    parser.add_argument("--baud", type=int, default=115200)
    parser.add_argument("--log", type=Path, help="Save received lines verbatim")
    parser.add_argument("--command", action="append", default=[], choices=sorted(COMMANDS))
    parser.add_argument("--no-input", action="store_true")
    parser.add_argument("--duration", type=float, default=0, help="0 = until Ctrl-C")
    parser.add_argument("--replay", type=Path, help="Print a saved log without a serial device")
    args = parser.parse_args(argv)
    if args.replay:
        print(args.replay.read_text(), end="")
        return 0
    if not args.port:
        parser.error("--port is required unless using --replay")
    try:
        import serial
    except ImportError:
        parser.error("pyserial missing: python3 -m pip install -r tools/requirements.txt")
    outgoing = queue.Queue()
    for command in args.command:
        outgoing.put(command)

    def console():
        for line in sys.stdin:
            try:
                outgoing.put(normalized_command(line))
            except ValueError as error:
                print(error, file=sys.stderr)

    if not args.no_input:
        threading.Thread(target=console, daemon=True).start()
    saved = args.log.open("a", encoding="utf-8") if args.log else None
    try:
        with serial.Serial(args.port, args.baud, timeout=0.05, write_timeout=1) as port:
            started = time.monotonic()
            pending = bytearray()
            while not args.duration or time.monotonic() - started < args.duration:
                while not outgoing.empty():
                    port.write((outgoing.get_nowait() + "\n").encode("ascii"))
                pending.extend(port.read(max(1, min(port.in_waiting, 4096))))
                while b"\n" in pending:
                    raw, _, rest = pending.partition(b"\n")
                    pending[:] = rest
                    line = raw.decode("utf-8", errors="replace").rstrip("\r")
                    print(line, flush=True)
                    if saved:
                        saved.write(line + "\n")
                        saved.flush()
                if len(pending) > 8192:
                    print("Dropped overlong unterminated serial line", file=sys.stderr)
                    pending.clear()
    except KeyboardInterrupt:
        pass
    except (serial.SerialException, OSError) as error:
        print(f"Monitor error: {error}", file=sys.stderr)
        return 1
    finally:
        if saved:
            saved.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
