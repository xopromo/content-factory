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
    script_path = ROOT / "scripts" / "process_pending_tasks.py"
    try:
        # Run process_pending_tasks.py in a subprocess
        res = subprocess.run(
            [sys.executable, str(script_path)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
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

def handle_chatops_request(ws, request_id, command, args):
    import base64
    import tempfile
    import shutil
    import ctypes
    import subprocess
    from PIL import ImageGrab
    
    log.info("Processing ChatOps request #%s: %s (args: %s)", request_id, command, args)
    
    status = "ok"
    output = ""
    extra_data = {}
    
    try:
        if command == "status":
            # RAM
            class MEMORYSTATUSEX(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_ulong),
                    ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong),
                    ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong),
                    ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong),
                    ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
                ]
            stat = MEMORYSTATUSEX()
            stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat))
            total_ram = stat.ullTotalPhys / (1024 ** 3)
            free_ram = stat.ullAvailPhys / (1024 ** 3)
            used_ram = total_ram - free_ram
            ram_percent = stat.dwMemoryLoad
            
            # Disk
            total_d, used_d, free_d = shutil.disk_usage("C:\\")
            total_disk = total_d / (1024 ** 3)
            free_disk = free_d / (1024 ** 3)
            used_disk = used_d / (1024 ** 3)
            disk_percent = (used_d / total_d) * 100
            
            # CPU
            cpu_load = "N/A"
            try:
                out = subprocess.check_output("wmic cpu get loadpercentage", shell=True, text=True)
                lines = [line.strip() for line in out.splitlines() if line.strip()]
                if len(lines) > 1:
                    cpu_load = f"{lines[1]}%"
            except Exception:
                pass
                
            output = (
                f"💻 <b>Локальный ПК (Системный отчет):</b>\n\n"
                f"🧠 <b>RAM:</b> Total={total_ram:.1f}GB, Used={used_ram:.1f}GB, Free={free_ram:.1f}GB ({ram_percent}%)\n"
                f"💾 <b>Disk C::</b> Total={total_disk:.1f}GB, Used={used_disk:.1f}GB, Free={free_disk:.1f}GB ({disk_percent:.1f}%)\n"
                f"⚡ <b>CPU Load:</b> {cpu_load}"
            )
            
        elif command == "screenshot":
            tmp_path = Path(tempfile.gettempdir()) / f"scr_{request_id}.png"
            try:
                img = ImageGrab.grab()
                img.save(tmp_path, "PNG")
                with open(tmp_path, "rb") as f:
                    b64_data = base64.b64encode(f.read()).decode("utf-8")
                extra_data["image_b64"] = b64_data
                output = "Скриншот успешно захвачен!"
            except Exception as e:
                log.error("Screenshot capture failed: %s", e)
                raise Exception(f"Не удалось сделать скриншот: {e}")
            finally:
                if tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except Exception:
                        pass
                    
        elif command == "cmd":
            cmd_str = " ".join(args)
            res = subprocess.run(cmd_str, capture_output=True, text=True, encoding="utf-8", errors="replace", shell=True, timeout=45)
            output = ""
            if res.stdout:
                output += res.stdout
            if res.stderr:
                output += f"\n[ERROR]\n{res.stderr}"
            if not output:
                output = "[No Output]"
                
        elif command == "ls":
            path_str = args[0] if args else "."
            target_path = Path(path_str).resolve()
            if not target_path.exists():
                raise Exception(f"Путь {target_path} не существует.")
            if target_path.is_file():
                raise Exception(f"Путь {target_path} является файлом, а не директорией.")
                
            items = []
            for item in target_path.iterdir():
                is_dir = "[DIR]" if item.is_dir() else "[FILE]"
                size = "" if item.is_dir() else f" ({item.stat().st_size / 1024:.1f} KB)"
                items.append(f"{is_dir} {item.name}{size}")
            
            output = f"📁 <b>Содержимое {target_path}:</b>\n\n" + "\n".join(items[:100])
            if len(items) > 100:
                output += f"\n... и еще {len(items) - 100} элементов."
                
        elif command == "cat":
            if not args:
                raise Exception("Не указан путь к файлу.")
            file_path = Path(args[0]).resolve()
            if not file_path.exists():
                raise Exception(f"Файл {file_path} не найден.")
            if not file_path.is_file():
                raise Exception(f"Путь {file_path} не является файлом.")
                
            # Limit read to 100KB to avoid flooding
            if file_path.stat().st_size > 150 * 1024:
                raise Exception("Файл слишком большой для просмотра через cat. Используйте download.")
                
            output = file_path.read_text(encoding="utf-8", errors="replace")
            
        elif command == "download":
            if not args:
                raise Exception("Не указан путь к файлу.")
            file_path = Path(args[0]).resolve()
            if not file_path.exists():
                raise Exception(f"Файл {file_path} не найден.")
            if not file_path.is_file():
                raise Exception(f"Путь {file_path} не является файлом.")
            
            size_mb = file_path.stat().st_size / (1024 * 1024)
            if size_mb > 45.0:
                raise Exception(f"Файл слишком большой ({size_mb:.1f} MB). Максимум 45 MB.")
                
            with open(file_path, "rb") as f:
                b64_data = base64.b64encode(f.read()).decode("utf-8")
            extra_data["file_b64"] = b64_data
            extra_data["filename"] = file_path.name
            output = f"Файл {file_path.name} успешно подготовлен к передаче."
            
        elif command == "upload":
            if len(args) < 2:
                raise Exception("Недостаточно аргументов для загрузки.")
            dest_path_str = args[0]
            file_b64 = args[1]
            dest_path = Path(dest_path_str).resolve()
            dest_path.parent.mkdir(parents=True, exist_ok=True)
            
            file_bytes = base64.b64decode(file_b64)
            with open(dest_path, "wb") as f:
                f.write(file_bytes)
            output = f"Файл успешно сохранен на ПК: {dest_path}"
            
        elif command == "log":
            log_path = log_file
            if not log_path.exists():
                raise Exception("Лог-файл клиента не найден.")
            content = log_path.read_text(encoding="utf-8", errors="replace")
            # Last 50 lines
            lines = content.splitlines()
            output = "\n".join(lines[-50:])
            
        else:
            raise Exception(f"Неизвестная команда ChatOps: {command}")
            
    except Exception as e:
        status = "error"
        output = f"Ошибка выполнения команды: {str(e)}"
        log.error("Error executing ChatOps command %s: %s", command, e)
        
    try:
        response = {
            "type": "chatops_response",
            "request_id": request_id,
            "status": status,
            "output": output,
            "extra_data": extra_data
        }
        log.info("Sending chatops_response #%s back to server. Status: %s", request_id, status)
        ws.send(json.dumps(response))
    except Exception as se:
        log.error("Failed to send ChatOps response over socket: %s", se)

def on_message(ws, message):
    try:
        # Don't print the huge base64 data to console/log
        if '"type": "transcribe_request"' in message or '"type": "chatops_request"' in message:
            log.info("Received message: request (large data omitted)")
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
        elif msg_type == "chatops_request":
            request_id = data.get("request_id")
            command = data.get("command")
            args = data.get("args", [])
            
            import threading
            threading.Thread(
                target=handle_chatops_request,
                args=(ws, request_id, command, args),
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
            t_start = time.time()
            # This blocks until connection is closed
            ws.run_forever(ping_interval=30, ping_timeout=10)
            if time.time() - t_start > 10:
                backoff = 2
        except Exception as e:
            log.error("WebSocket run_forever crashed: %s", e)
            
        log.info("Reconnecting in %d seconds...", backoff)
        time.sleep(backoff)
        backoff = min(backoff * 2, 60)

if __name__ == "__main__":
    log.info("Jarvis WebSocket Wakeup Client starting...")
    start_client()
