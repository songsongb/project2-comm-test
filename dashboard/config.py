from pathlib import Path
import os

ROOT = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("DASHBOARD_DATA_DIR", ROOT / "data"))
BAUD = 115200
TARGET_HZ = 10000
CPU_HZ = 64000000
FRESH_SECONDS = 3.0
STATUS_SECONDS = 2.5
MODES = {0: "Polling", 1: "Interrupt", 2: "DMA"}
DEVICES = ("window", "door", "hub", "uno")
LABELS = {"window": "STM32 #1 · Window", "door": "STM32 #2 · Door",
          "hub": "STM32 #3 · Hub", "uno": "Arduino #4"}
ALLOWED = ("STATUS", "HELP", "MODE 0", "MODE 1", "MODE 2", "LOAD 0", "LOAD 1", "CAL")
