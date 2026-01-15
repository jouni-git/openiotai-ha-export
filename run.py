import json
import os
import sys
import asyncio
from datetime import datetime
import re
import ssl

import paho.mqtt.client as mqtt

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
    unit = re.sub(r"[^a-zA-Z0-9]+", "_", unit)

    return unit.strip("_")


# ---------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------

def init_mqtt_client(options):
    host = options.get("mqtt_host")
    port = int(options.get("mqtt_port", 8883))
    username = options.get("mqtt_username")
    password = options.get("mqtt_password")

    if not host:
        fatal("Missing required option: mqtt_host (set it in the add-on Configuration tab)")

    client = mqtt.Client(protocol=mqtt.MQTTv311)

    if username and password:
        client.username_pw_set(username, password)

    client.tls_set(
        cert_reqs=ssl.CERT_REQUIRED,
        tls_version=ssl.PROTOCOL_TLS_CLIENT,
    )
    client.tls_insecure_set(False)

    try:
        client.connect(host, port, keepalive=60)
    except Exception as e:
        fatal(f"Failed to connect to MQTT broker via TLS: {e}")

    log("INFO", f"Connected to MQTT broker {host}:{port} (TLS)")
    return client


def mqtt_publish(client, topic: str, payload: dict):
    data = json.dumps(payload, ensure_ascii=False)

    # Always show preview
    log("MQTT_PREVIEW", data)

    try:
        client.publish(topic, data, qos=0, retain=False)
    except Exception as e:
        log("ERROR", f"MQTT publish failed: {e}")


# ---------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------

def build_sensor_payload(entity_id: str, value, unit: str | None):
    key = f"{entity_id}_{unit}" if unit else entity_id
    return {key: value}


def build_heartbeat_payload(gateway_id: str, counter: int):
    return {f"heartbeat.gateway.{gateway_id}": counter}


# ---------------------------------------------------------------------
# Home Assistant WebSocket listener
# ---------------------------------------------------------------------

async def ha_event_listener(gateway_id, mqtt_client, mqtt_topic):
    try:
        import websockets
    except Exception:
        fatal("Python dependency 'websockets' not found")

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        fatal("SUPERVISOR_TOKEN not found")

    log("INFO", f"Connecting to Home Assistant WebSocket at {HA_WS_URL}")

    async with websockets.connect(HA_WS_URL) as ws:
        msg = json.loads(await ws.recv())
        if msg.get("type") != "auth_required":
            fatal(f"Unexpected WS message: {msg}")

        await ws.send(json.dumps({
            "type": "auth",
            "access_token": token,
        }))

        msg = json.loads(await ws.recv())
        if msg.get("type") != "auth_ok":
            fatal(f"Authentication failed: {msg}")

        log("INFO", "Authenticated to Home Assistant WebSocket")

        await ws.send(json.dumps({
            "id": 1,
            "type": "subscribe_events",
            "event_type": "state_changed",
        }))

        log("INFO", "Subscribed to state_changed events")

        while True:
            event = json.loads(await ws.recv())
            if event.get("type") != "event":
                continue

            data = event.get("event", {}).get("data", {})
            entity_id = data.get("entity_id")

            new_state = data.get("new_state")
            if not new_state:
                continue

            try:
                value = float(new_state.get("state"))
            except Exception:
                continue

            attrs = new_state.get("attributes", {})
            unit = normalize_unit(attrs.get("unit_of_measurement"))

            payload = build_sensor_payload(entity_id, value, unit)
            mqtt_publish(mqtt_client, mqtt_topic, payload)


# ---------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------

async def heartbeat_loop(gateway_id, interval, mqtt_client, mqtt_topic):
    counter = 0
    log("INFO", "Heartbeat loop started")

    while True:
        await asyncio.sleep(interval)
        counter += 1
        payload = build_heartbeat_payload(gateway_id, counter)
        mqtt_publish(mqtt_client, mqtt_topic, payload)


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

    mqtt_topic = options.get("mqtt_topic")
    if not mqtt_topic or not isinstance(mqtt_topic, str):
        fatal("Missing required option: mqtt_topic (set it in the add-on Configuration tab)")
    mqtt_topic = mqtt_topic.strip()
    if not mqtt_topic:
        fatal("mqtt_topic is empty (set it in the add-on Configuration tab)")

    mqtt_client = init_mqtt_client(options)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(
        asyncio.gather(
            ha_event_listener(gateway_id, mqtt_client, mqtt_topic),
            heartbeat_loop(gateway_id, interval, mqtt_client, mqtt_topic),
        )
    )


if __name__ == "__main__":
    main()
