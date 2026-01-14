import sys
import time
from datetime import datetime
import os


def log(msg):
    sys.stdout.write(msg + "\n")
    sys.stdout.flush()


log("=== OPENIOTAI ADD-ON STARTING ===")
log(f"PID={os.getpid()}")
log(f"PYTHON={sys.version}")
log(f"CWD={os.getcwd()}")

counter = 0
while True:
    log(f"[{datetime.utcnow().isoformat()}] OPENIOTAI ADDON ALIVE – heartbeat={counter}")
    counter += 1
    time.sleep(10)
