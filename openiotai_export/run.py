import time
from datetime import datetime

def log(msg):
    print(f"[{datetime.utcnow().isoformat()}] {msg}", flush=True)

log("Starting OpenIOTAI MQTT Export add-on")

while True:
    time.sleep(30)
    log("OpenIOTAI Export add-on is running")
