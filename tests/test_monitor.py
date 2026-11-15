import importlib.util
import os
import select
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("monitor", ROOT / "tools/monitor.py")
monitor = importlib.util.module_from_spec(spec)
spec.loader.exec_module(monitor)


class MonitorTests(unittest.TestCase):
    def test_command_validation(self):
        self.assertEqual(monitor.normalized_command(" disarm\r\n"), "DISARM")
        with self.assertRaises(ValueError):
            monitor.normalized_command("ARM\nDISARM")

    def test_offline_replay(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "replay.txt"
            path.write_text("t=1 node=3 event=STATUS state=ARMED gpio=0\n")
            result = subprocess.run([sys.executable, str(ROOT / "tools/monitor.py"),
                                     "--replay", str(path)], capture_output=True, text=True, check=True)
            self.assertEqual(result.stdout, path.read_text())

    @unittest.skipUnless(importlib.util.find_spec("serial"), "pyserial not installed")
    def test_pyserial_pseudoterminal_fragmented_logs_and_command(self):
        import pty
        master, slave = pty.openpty()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                logfile = Path(tmp) / "monitor.txt"
                with subprocess.Popen([sys.executable, str(ROOT / "tools/monitor.py"),
                                       "--port", os.ttyname(slave), "--command", "STATUS",
                                       "--no-input", "--duration", "1", "--log", str(logfile)],
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True) as process:
                    command = bytearray()
                    deadline = time.monotonic() + 3
                    while b"STATUS\n" not in command and time.monotonic() < deadline:
                        if select.select([master], [], [], 0.1)[0]:
                            command.extend(os.read(master, 128))
                    self.assertIn(b"STATUS\n", command)
                    os.write(master, b"t=100 node=3 event=STA")
                    os.write(master, b"TUS state=DISARMED gpio=0\r\n")
                    stdout, stderr = process.communicate(timeout=5)
                    self.assertEqual(process.returncode, 0, stderr)
                    self.assertIn("state=DISARMED gpio=0\n", stdout)
                    self.assertEqual(logfile.read_text(), stdout)
        finally:
            os.close(master)
            os.close(slave)
