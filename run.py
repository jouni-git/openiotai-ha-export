import json
import os
import sys
import time
import asyncio
from datetime import datetime

OPTIONS_FILE = "/data/options.json"
HA_WS_URL = "ws://supervisor/core/api/websocket"

# --- logging ---------------------------------------------------------------

def log(level: str, msg: str):
    ts = datetime.utcnow().isoformat()
    sys.stdout.write(f"[{ts}] [{level}] {msg}\n")
    sys.stdout.flush()


def fatal(msg: str, exit_code: int = 1):
    log("FATAL", msg)
    sys.exit(exit_code)


# --- config ----------------------------------------------------------------

def load_options():
    log("INFO", f"Loading options from {OPTIONS_FILE}")

    if not os.path.exists(OPTIONS_FILE):
        fatal(f"Options file not found: {OPTIONS_FILE}")

    try:
        with open(OPTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        fatal(f"Invalid JSON in options file: {e}")
    except Exception as e:
        fatal(f"Failed to read options file: {e}")


def validate_heartbeat_interval(value):
    if not isinstance(value, int):
        fatal(f"heartbeat_interval_seconds must be int, got {type(value)}")

    if value <= 0:
        fatal("heartbeat_interval_seconds must be > 0")

    if value < 5:
        log("WARN", f"heartbeat_interval_seconds={value} is very low")

    return value


# --- Home Assistant WebSocket ----------------------------------------------

async def ha_event_listener():
    try:
        import websockets
    except Exception:
        fatal(
            "Python dependency 'websockets' not found. "
            "Add it to the image before enabling HA event listening."
        )

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        fatal("SUPERVISOR_TOKEN not found in environment")

    log("INFO", f"Connecting to Home Assistant WebSocket at {HA_WS_URL}")

    try:
        async with websockets.connect(HA_WS_URL) as ws:
            # 1. Receive auth_required
            msg = json.loads(await ws.recv())
            if msg.get("type") != "auth_required":
                fatal(f"Unexpected WS message: {msg}")

            # 2. Send auth
            await ws.send(
                json.dumps(
                    {
                        "type": "auth",
                        "access_token": token,
                    }
                )
            )

            # 3. Receive auth_ok
            msg = json.loads(await ws.recv())
            if msg.get("type") != "auth_ok":
                fatal(f"Authentication failed: {msg}")

            log("INFO", "Authenticated to Home Assistant WebSocket")

            # 4. Subscribe to state_changed events
            await ws.send(
                json.dumps(
                    {
                        "id": 1,
                        "type": "subscribe_events",
                        "event_type": "state_changed",
                    }
                )
            )

            log("INFO", "Subscribed to state_changed events")

            # 5. Event loop
            while True:
                raw = await ws.recv()
                event = json.loads(raw)

                if event.get("type") != "event":
                    continue

                data = event.get("event", {}).get("data", {})
                entity_id = data.get("entity_id")

                old_state = data.get("old_state", {})
                new_state = data.get("new_state", {})

                old_val = old_state.get("state")
                new_val = new_state.get("state")

                attrs = new_state.get("attributes", {})
                unit = attrs.get("unit_of_measurement")

                log(
                    "EVENT",
                    f"{entity_id}: {old_val} -> {new_val}"
                    + (f" {unit}" if unit else ""),
                )

    except Exception as e:
        log("ERROR", f"Home Assistant WS listener crashed: {e}")
        await asyncio.sleep(5)
        fatal("HA event listener terminated")


# --- heartbeat --------------------------------------------------------------

async def heartbeat_loop(gateway_id: str, interval: int):
    log("INFO", "Heartbeat loop started")
    counter = 0
    start_ts = int(time.time())

    while True:
        await asyncio.sleep(interval)
        uptime = int(time.time()) - start_ts
        log(
            "HEARTBEAT",
            f"gateway_id={gateway_id} count={counter} uptime_seconds={uptime}",
        )
        counter += 1


# --- main ------------------------------------------------------------------

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
        f"Configuration loaded (gateway_id={gateway_id}, heartbeat_interval_seconds={heartbeat_interval})",
    )

    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        asyncio.gather(
            heartbeat_loop(gateway_id, heartbeat_interval),
            ha_event_listener(),
        )
    )


if __name__ == "__main__":
    main()
