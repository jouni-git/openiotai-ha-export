import json
import os
import sys
import time
from datetime import datetime


OPTIONS_FILE = "/data/options.json"


def log(level: str, msg: str):
    ts = datetime.utcnow().isoformat()
    sys.stdout.write(f"[{ts}] [{level}] {msg}\n")
    sys.stdout.flush()


def fatal(msg: str, exit_code: int = 1):
    log("FATAL", msg)
    sys.exit(exit_code)


def load_options():
    log("INFO", f"Loading options from {OPTIONS_FILE}")

    if not os.path.exists(OPTIONS_FILE):
        fatal(f"Options file not found: {OPTIONS_FILE}")

    try:
        with open(OPTIONS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        fatal(f"Invalid JSON in options file: {e}")
    except Exception as e:
        fatal(f"Failed to read options file: {e}")

    return data


def validate_heartbeat_interval(value):
    if not isinstance(value, int):
        fatal(f"heartbeat_interval_seconds must be int, got {type(value)}")

    if value <= 0:
        fatal("heartbeat_interval_seconds must be > 0")

    if value < 5:
        log(
            "WARN",
            f"heartbeat_interval_seconds={value} is very low and may cause unnecessary load",
        )

    return value


def main():
    log("INFO", "=== OPENIOTAI ADD-ON STARTING ===")
    log("INFO", f"PID={os.getpid()}")
    log("INFO", f"PYTHON={sys.version}")
    log("INFO", f"CWD={os.getcwd()}")

    options = load_options()

    if "heartbeat_interval_seconds" not in options:
        fatal("Missing required option: heartbeat_interval_seconds")

    heartbeat_interval = validate_heartbeat_interval(
        options["heartbeat_interval_seconds"]
    )

    gateway_id = options.get("gateway_id", "unknown")

    log(
        "INFO",
        f"Configuration loaded successfully (gateway_id={gateway_id}, heartbeat_interval_seconds={heartbeat_interval})",
    )

    log("INFO", "Entering heartbeat loop")

    counter = 0
    last_heartbeat = time.time()

    while True:
        try:
            now = time.time()
            elapsed = now - last_heartbeat

            if elapsed >= heartbeat_interval:
                log(
                    "HEARTBEAT",
                    f"gateway_id={gateway_id} count={counter} uptime_seconds={int(now)}",
                )
                counter += 1
                last_heartbeat = now

            time.sleep(1)

        except KeyboardInterrupt:
            log("INFO", "Shutdown requested (KeyboardInterrupt)")
            break
        except Exception as e:
            log("ERROR", f"Unhandled exception in main loop: {e}")
            time.sleep(5)


if __name__ == "__main__":
    main()
