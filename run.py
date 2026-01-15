import json
import os
import sys
import time
import asyncio
from datetime import datetime
import re

OPTIONS_FILE = "/data/options.json"
HA_WS_URL = "ws://supervisor/core/api/websocket"


# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

def log(level: str, msg: str):
    ts = datetime.utcnow().isoformat()
    sys.stdout.write(f"[{ts}] [{level}] {msg}\n")
    sys.stdout.flush()


def fatal(msg: str):
    log("FATAL", msg)
    sys.exit(1)


# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------

def load_options():
    if not os.path.exists(OPTIONS_FILE):
        fatal(f"Options file not found: {OPTIONS_FILE}")

    try:
        with open(OPTIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        fatal(f"Failed to load options.json: {e}")


# ---------------------------------------------------------------------
# Unit normalization
# ---------------------------------------------------------------------

UNIT_MAP = {
    "°C": "C",
    "°F": "F",
    "V": "V",
    "A": "A",
    "W": "W",
    "%": "pct",
    "hPa": "hPa",
}


def normalize_unit(unit: str | None) -> str | None:
    if not unit:
        return None

    unit = UNIT_MAP.get(unit, unit)

    # Allow only safe characters for keys
    unit = re.sub(r"[^a-zA-Z0-9]+", "_", unit)

    return unit.strip("_")


# ---------------------------------------------------------------------
# MQTT payload builders (LOG ONLY)
# ---------------------------------------------------------------------

def build_sensor_payload(entity_id: str, value, unit: str | None):
    if unit:
        key = f"{entity_id}_{unit}"
    else:
        key = entity_id

    return {key: value}


def build_heartbeat_payload(gateway_id: str, counter: int):
    return {f"heartbeat.gateway.{gateway_id}": counter}


# ---------------------------------------------------------------------
# Home Assistant WebSocket listener
# ---------------------------------------------------------------------

async def ha_event_listener(gateway_id: str):
    try:
        import websockets
    except Exception:
        fatal("Python dependency 'websockets' not found")

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        fatal("SUPERVISOR_TOKEN not found")

    log("INFO", f"Connecting to Home Assistant WebSocket at {HA_WS_URL}")

    async with websockets.connect(HA_WS_URL) as ws:
        # auth_required
        msg = json.loads(await ws.recv())
        if msg.get("type") != "auth_required":
            fatal(f"Unexpected WS message: {msg}")

        # auth
        await ws.send(json.dumps({
            "type": "auth",
            "access_token": token,
        }))

        # auth_ok
        msg = json.loads(await ws.recv())
        if msg.get("type") != "auth_ok":
            fatal(f"Authentication failed: {msg}")

        log("INFO", "Authenticated to Home Assistant WebSocket")

        # subscribe
        await ws.send(json.dumps({
            "id": 1,
            "type": "subscribe_events",
            "event_type": "state_changed",
        }))

        log("INFO", "Subscribed to state_changed events")

        while True:
            raw = await ws.recv()
            event = json.loads(raw)

            if event.get("type") != "event":
                continue

            data = event.get("event", {}).get("data", {})
            entity_id = data.get("entity_id")

            new_state = data.get("new_state")
            if not new_state:
                continue

            value = new_state.get("state")
            try:
                value = float(value)
            except Exception:
                continue  # skip non-numeric

            attrs = new_state.get("attributes", {})
            unit_raw = attrs.get("unit_of_measurement")
            unit = normalize_unit(unit_raw)

            payload = build_sensor_payload(entity_id, value, unit)

            log("MQTT_PREVIEW", json.dumps(payload, ensure_ascii=False))


# ---------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------

async def heartbeat_loop(gateway_id: str, interval: int):
    counter = 0
    log("INFO", "Heartbeat loop started")

    while True:
        await asyncio.sleep(interval)
        counter += 1
        payload = build_heartbeat_payload(gateway_id, counter)
        log("MQTT_PREVIEW", json.dumps(payload))


# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    log("INFO", "=== OPENIOTAI ADD-ON STARTING ===")
    log("INFO", f"PID={os.getpid()}")
    log("INFO", f"PYTHON={sys.version}")

    options = load_options()

    gateway_id = options.get("gateway_id", "unknown")
    interval = int(options.get("heartbeat_interval_seconds", 15))

    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        asyncio.gather(
            ha_event_listener(gateway_id),
            heartbeat_loop(gateway_id, interval),
        )
    )


if __name__ == "__main__":
    main()
