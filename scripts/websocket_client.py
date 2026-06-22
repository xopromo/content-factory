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

_whisper_model = None

def get_whisper_model():
    global _whisper_model
    if _whisper_model is None:
        log.info("Initializing faster-whisper model ('base', CPU)...")
        try:
            from faster_whisper import WhisperModel
            # Load the 'base' model on CPU, compute_type="int8" for fast CPU execution
            _whisper_model = WhisperModel("base", device="cpu", compute_type="int8")
            log.info("faster-whisper model loaded successfully!")
        except Exception as e:
            log.error("Failed to load faster-whisper model: %s", e)
            raise e
    return _whisper_model

def transcribe_audio_locally(file_path):
    try:
        model = get_whisper_model()
        log.info("Starting local transcription for: %s", file_path)
        t0 = time.time()
        
        segments, info = model.transcribe(str(file_path), beam_size=5, language="ru")
        segments = list(segments)  # Trigger actual transcription execution
        
        text = "".join(segment.text for segment in segments).strip()
        duration = info.duration
        elapsed = time.time() - t0
        
        log.info("Transcription completed in %.2fs (audio duration: %.2fs)", elapsed, duration)
        return text, None
    except Exception as e:
        log.error("Local transcription error: %s", e)
        return None, str(e)

def handle_transcribe_request(ws, request_id, audio_b64, file_ext):
    import base64
    import tempfile
    
    tmp_path = None
    try:
        # Decode base64
        audio_bytes = base64.b64decode(audio_b64)
        
        # Write to temp file
        with tempfile.NamedTemporaryFile(suffix=file_ext, delete=False) as tmp:
            tmp.write(audio_bytes)
            tmp_path = Path(tmp.name)
            
        # Transcribe
        text, err = transcribe_audio_locally(tmp_path)
        
        # Send response
        response = {
            "type": "transcribe_response",
            "request_id": request_id,
            "text": text,
            "error": err
        }
        ws.send(json.dumps(response))
        log.info("Sent transcribe_response #%s back to server", request_id)
    except Exception as e:
        log.error("Error in handle_transcribe_request: %s", e)
        try:
            ws.send(json.dumps({
                "type": "transcribe_response",
                "request_id": request_id,
                "text": None,
                "error": str(e)
            }))
        except Exception:
            pass
    finally:
        if tmp_path and tmp_path.exists():
            try:
                tmp_path.unlink()
            except Exception:
                pass

def on_message(ws, message):
    try:
        # Don't print the huge base64 audio data to console/log
        if '"type": "transcribe_request"' in message:
            log.info("Received message: transcribe_request (large audio data omitted)")
        else:
            log.info("Received message: %s", message)
            
        data = json.loads(message)
        msg_type = data.get("type")
        
        if msg_type == "wakeup":
            log.info("Wakeup signal received for task #%s", data.get("task_id"))
            run_task_processor()
        elif msg_type == "transcribe_request":
            request_id = data.get("request_id")
            audio_b64 = data.get("audio_data")
            file_ext = data.get("file_ext", ".ogg")
            
            import threading
            threading.Thread(
                target=handle_transcribe_request,
                args=(ws, request_id, audio_b64, file_ext),
                daemon=True
            ).start()
    except Exception as e:
        log.error("Failed to process message: %s", e)

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
