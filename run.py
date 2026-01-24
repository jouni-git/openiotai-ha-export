import json, os, sys, asyncio, signal
from datetime import datetime
import paho.mqtt.client as mqtt
import re

OPTIONS_FILE = "/data/options.json"
HA_WS_URL = "ws://supervisor/core/api/websocket"
shutdown_event = asyncio.Event()

# ---------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------

def log(level, msg):
    sys.stdout.write(f"[{datetime.utcnow().isoformat()}] [{level}] {msg}\n")
    sys.stdout.flush()

def fatal(msg):
    log("FATAL", msg)
    sys.exit(1)

# ---------------------------------------------------------------------
# Shutdown handling
# ---------------------------------------------------------------------

def shutdown(signum, frame):
    log("INFO", f"Shutdown signal {signum}")
    shutdown_event.set()

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------

def load_options():
    try:
        with open(OPTIONS_FILE, "r", encoding="utf-8") as f: return json.load(f)
    except Exception as e: fatal(f"options.json error: {e}")

# ---------------------------------------------------------------------
# MQTT
# ---------------------------------------------------------------------

_CONTROL_CHARS = re.compile(r"[\x00-\x1F\x7F]")
def deep_clean(value):
    if isinstance(value, str):
        return _CONTROL_CHARS.sub("", value).strip()
    if isinstance(value, list):
        return [deep_clean(v) for v in value]
    if isinstance(value, dict):
        return {deep_clean(k): deep_clean(v) for k, v in value.items()}  # key + value
    return value



def mqtt_setup(o):
    c = mqtt.Client(protocol=mqtt.MQTTv311)
    if o.get("mqtt_username"): c.username_pw_set(o["mqtt_username"], o.get("mqtt_password"))
    c.tls_set()
    c.connect(o["mqtt_host"], int(o.get("mqtt_port", 8883)), 60)
    c.loop_start()
    log("INFO", "MQTT connected")
    return c


def publish(c, topic, payload):
    try:
        payload = deep_clean(payload)   # ← PAKOLLINEN
        data = json.dumps(payload, ensure_ascii=False)
        c.publish(topic, data, qos=1)
        log("MQTT_SENT", f"{len(data)} bytes")
    except Exception as e:
        log("MQTT_ERROR", str(e))


# ---------------------------------------------------------------------
# Home Assistant WebSocket listener
# ---------------------------------------------------------------------

async def ha_listener(c, topic, gateway_id):
    try:
        import websockets
    except Exception:
        fatal("websockets missing")

    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        fatal("SUPERVISOR_TOKEN missing")

    backoff = 1

    while not shutdown_event.is_set():
        try:
            async with websockets.connect(HA_WS_URL) as ws:
                json.loads(await ws.recv())
                await ws.send(json.dumps({"type": "auth", "access_token": token}))
                json.loads(await ws.recv())
                await ws.send(json.dumps({
                    "id": 1,
                    "type": "subscribe_events",
                    "event_type": "state_changed"
                }))
                backoff = 1

                while not shutdown_event.is_set():
                    try:
                        msg = json.loads(await ws.recv())
                    except Exception as e:
                        log("WS_ERROR", str(e))
                        break

                    if msg.get("type") != "event":
                        continue

                    ev = msg.get("event", {})
                    data = ev.get("data", {})

                    ns = data.get("new_state")
                    os_ = data.get("old_state")

                    if not ns or not os_:
                        continue

                    # --- Validate numeric measurement ---
                    try:
                        new_val = float(ns.get("state"))
                        old_val = float(os_.get("state"))
                    except Exception:
                        continue

                    # --- Ignore non-changing or transient updates ---
                    if new_val == old_val:
                        continue

                    publish(c, topic, {
                        "schema_version": 1,
                        "source": "homeassistant",
                        "ts": int(datetime.utcnow().timestamp() * 1000),
                        "gateway": {
                            "type": "ha_addon",
                            "gateway_id": gateway_id
                        },
                        "event": ev,
                    })



        except Exception as e:
            log("WS_WARN", str(e))

        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=backoff)
        except asyncio.TimeoutError:
            backoff = min(backoff * 2, 30)



# ---------------------------------------------------------------------
# Heartbeat
# ---------------------------------------------------------------------

async def heartbeat(c, topic, gateway_id, interval):
    counter = 0
    while not shutdown_event.is_set():
        try:
            await asyncio.wait_for(shutdown_event.wait(), timeout=interval)
        except asyncio.TimeoutError:
            counter += 1
            publish(c, topic, {
                "schema_version": 1,
                "source": "ha_addon",
                "ts": int(datetime.utcnow().timestamp() * 1000),
                "heartbeat": {"gateway_id": gateway_id, "counter": counter},
            })

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    log("INFO", "OPENIOTAI ADD-ON START")
    signal.signal(signal.SIGTERM, shutdown)
    signal.signal(signal.SIGINT, shutdown)

    o = load_options()
    c = mqtt_setup(o)

    asyncio.get_event_loop().run_until_complete(asyncio.gather(
        ha_listener(c, o["mqtt_topic"], o.get("gateway_id", "unknown")),
        heartbeat(c, o["mqtt_topic"], o.get("gateway_id", "unknown"),
                  int(o.get("heartbeat_interval_seconds", 15)))
    ))

if __name__ == "__main__":
    main()
