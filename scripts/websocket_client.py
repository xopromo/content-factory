# -*- coding: utf-8 -*-
import os
import sys
import json
import time
import subprocess
import logging
from pathlib import Path
from dotenv import load_dotenv

# Setup paths
ROOT = Path(__file__).parent.parent
load_dotenv(ROOT / ".env")

# Configure logging
log_file = ROOT / "websocket_client.log"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8", mode="a")
    ]
)
log = logging.getLogger("WSClient")

# Check if websocket-client is installed
try:
    import websocket
except ImportError:
    log.info("Installing websocket-client...")
    subprocess.run([sys.executable, "-m", "pip", "install", "websocket-client"], check=True)
    import websocket

def run_task_processor():
    log.info("Triggering process_pending_tasks.py...")
    script_path = Path("C:/Users/асус/.gemini/antigravity/brain/53b913fe-94c5-41ad-ad76-72fde5331225/scratch/process_pending_tasks.py")
    try:
        # Run process_pending_tasks.py in a subprocess
        res = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=180
        )
        log.info("Task processor finished with exit code %d", res.returncode)
        if res.stdout:
            log.info("Task processor stdout:\n%s", res.stdout.strip())
        if res.stderr:
            log.warning("Task processor stderr:\n%s", res.stderr.strip())
    except Exception as e:
        log.error("Failed to run task processor: %s", e)

def on_message(ws, message):
    log.info("Received message: %s", message)
    try:
        data = json.loads(message)
        if data.get("type") == "wakeup":
            log.info("Wakeup signal received for task #%s", data.get("task_id"))
            run_task_processor()
    except Exception as e:
        log.error("Failed to parse message: %s", e)

def on_error(ws, error):
    log.error("WebSocket error: %s", error)

def on_close(ws, close_status_code, close_msg):
    log.info("WebSocket connection closed: %s (code: %s)", close_msg, close_status_code)

def on_open(ws):
    log.info("WebSocket connection established! Listening for wakeups...")
    # Send a small identify ping
    ws.send(json.dumps({"type": "identify", "client": "pc_task_listener"}))

def start_client():
    # Determine WebSocket server URL
    render_url = os.getenv("RENDER_EXTERNAL_URL", "")
    if render_url:
        # Convert http/https to ws/wss
        if render_url.startswith("https://"):
            ws_url = render_url.replace("https://", "wss://").rstrip("/") + "/ws/wakeup"
        elif render_url.startswith("http://"):
            ws_url = render_url.replace("http://", "ws://").rstrip("/") + "/ws/wakeup"
        else:
            ws_url = f"wss://{render_url.rstrip('/')}/ws/wakeup"
    else:
        # Default to local server for testing
        ws_url = "ws://localhost:8080/ws/wakeup"
        
    log.info("Connecting to WebSocket server: %s", ws_url)
    
    # Run loop with reconnect backup
    backoff = 2
    while True:
        try:
            ws = websocket.WebSocketApp(
                ws_url,
                on_open=on_open,
                on_message=on_message,
                on_error=on_error,
                on_close=on_close
            )
            # This blocks until connection is closed
            ws.run_forever(ping_interval=30, ping_timeout=10)
        except Exception as e:
            log.error("WebSocket run_forever crashed: %s", e)
            
        log.info("Reconnecting in %d seconds...", backoff)
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)

if __name__ == "__main__":
    log.info("Jarvis WebSocket Wakeup Client starting...")
    start_client()
