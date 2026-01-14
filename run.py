import os
import time
from datetime import datetime


def log(msg: str):
    print(f"[{datetime.utcnow().isoformat()}] {msg}", flush=True)


def main():
    log("DUMMY ADD-ON STARTED")
    log(f"PID: {os.getpid()}")
    log(f"ENV VARS: {list(os.environ.keys())[:10]}")

    counter = 0
    while True:
        log(f"Dummy heartbeat {counter}")
        counter += 1
        time.sleep(10)


if __name__ == "__main__":
    main()
