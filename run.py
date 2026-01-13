import json
import ssl
import time
from datetime import datetime
from pathlib import Path

import requests
import paho.mqtt.client as mqtt


CONFIG_PATH = "/data/options.json"
CA_CACHE_PATH = "/data/ca.pem"


def log(msg: str):
    print(f"[{datetime.utcnow().isoformat()}] {msg}", flush=True)


def load_config() -> dict:
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def validate_config(cfg: dict):
    required = [
        "mqtt_host",
        "mqtt_port",
        "mqtt_username",
        "mqtt_password",
        "mqtt_topic",
        "gateway_id",
        "tls_ca_url",
    ]

    for key in required:
        if key not in cfg or not str(cfg[key]).strip():
            raise RuntimeError(f"Missing required config value: {key}")


def ensure_ca(ca_url: str) -> str:
    """
    Download CA certificate over HTTPS if not already cached.
    Returns path to CA file.
    """
    ca_path = Path(CA_CACHE_PATH)

    if ca_path.exists():
        log("Using cached CA certificate")
        return str(ca_path)

    log(f"Downloading CA certificate from {ca_url}")
    resp = requests.get(ca_url, timeout=15)
    resp.raise_for_status()

    ca_path.write_bytes(resp.content)
    log("CA certificate downloaded and cached")

    return str(ca_path)


def connect_mqtt_with_retry(client: mqtt.Client, host: str, port: int):
    """
    Keep retrying MQTT connection with backoff until successful.
    """
    delay = 5
    while True:
        try:
            client.connect(host, port, keepalive=60)
            log("MQTT connection established")
            return
        except Exception as e:
            log(f"MQTT connect failed, retrying in {delay}s: {e}")
            time.sleep(delay)
            delay = min(delay * 2, 60)


def main():
    log("Starting OpenIOTAI MQTT Export add-on")

    cfg = load_config()
    validate_config(cfg)

    ca_file = ensure_ca(cfg["tls_ca_url"])

    log(
        f"Connecting to MQTT broker {cfg['mqtt_host']}:{cfg['mqtt_port']} "
        f"as user '{cfg['mqtt_username']}' using TLS"
    )

    client = mqtt.Client(client_id=cfg["gateway_id"])
    client.username_pw_set(cfg["mqtt_username"], cfg["mqtt_password"])

    # TLS configuration (explicit and strict)
    tls_context = ssl.create_default_context(cafile=ca_file)
    tls_context.check_hostname = True
    tls_context.verify_mode = ssl.CERT_REQUIRED
    client.tls_set_context(tls_context)

    connect_mqtt_with_retry(
        client,
        cfg["mqtt_host"],
        int(cfg["mqtt_port"]),
    )

    client.loop_start()

    # Startup test message
    payload = {
        "gateway_id": cfg["gateway_id"],
        "timestamp": datetime.utcnow().isoformat(),
        "type": "startup",
        "message": "OpenIOTAI MQTT Export started successfully",
    }

    client.publish(cfg["mqtt_topic"], json.dumps(payload), qos=1)
    log(f"Startup message published to topic '{cfg['mqtt_topic']}'")

    # Keep container alive
    while True:
        time.sleep(30)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"FATAL ERROR: {e}")
        raise
