import os
import sys
import time
import socket
import subprocess
from datetime import datetime

# TCP Lock to prevent duplicate supervisor instances
LOCK_PORT = 28099
try:
    lock_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    lock_socket.bind(('127.0.0.1', LOCK_PORT))
    lock_socket.listen(1)
except socket.error:
    print(f"[{datetime.now()}] Supervisor is already running on port {LOCK_PORT}. Exiting.")
    sys.exit(0)

# Paths
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PARENT = os.path.dirname(ROOT)

SUPERVISOR_LOG = os.path.join(ROOT, "supervisor.log")

def log(message):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    entry = f"[{timestamp}] {message}\n"
    print(entry, end="")
    try:
        with open(SUPERVISOR_LOG, "a", encoding="utf-8") as f:
            f.write(entry)
    except Exception as e:
        print(f"Failed to write to supervisor log: {e}")

# Services configuration
SERVICES = [
    {
        "name": "websocket_client",
        "cmd": [sys.executable, "-u", "scripts/websocket_client.py"],
        "cwd": ROOT,
        "log": os.path.join(ROOT, "websocket_client.log")
    },
    {
        "name": "task_listener",
        "cmd": [sys.executable, "-u", "scripts/task_listener.py"],
        "cwd": ROOT,
        "log": os.path.join(ROOT, "task_listener.log")
    },
    {
        "name": "telegram_monitor_listener",
        "cmd": [sys.executable, "-u", "scripts/telegram_monitor_listener.py"],
        "cwd": ROOT,
        "log": os.path.join(ROOT, "telegram_monitor_listener.log")
    }
]

processes = {}
log_files = {}

def start_service(service):
    name = service["name"]
    cmd = service["cmd"]
    cwd = service["cwd"]
    log_path = service["log"]
    
    log(f"Starting service: {name} in {cwd}")
    try:
        log_file = open(log_path, "a", encoding="utf-8", buffering=1)
        log_files[name] = log_file
        
        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=log_file,
            stderr=subprocess.STDOUT,
            text=True
        )
        processes[name] = proc
        log(f"Service {name} started successfully with PID {proc.pid}")
    except Exception as e:
        log(f"[ERROR] Failed to start service {name}: {e}")

def main():
    log("=== JARVIS DAEMON SUPERVISOR STARTED ===")
    
    # Start all services
    for service in SERVICES:
        start_service(service)
        time.sleep(1) # stagger startup slightly
        
    try:
        while True:
            time.sleep(5)
            for service in SERVICES:
                name = service["name"]
                proc = processes.get(name)
                
                if proc is None:
                    log(f"[WARN] Service {name} has no running process object. Attempting restart...")
                    start_service(service)
                    continue
                    
                # Poll process status
                exit_code = proc.poll()
                if exit_code is not None:
                    log(f"[CRITICAL] Service {name} (PID {proc.pid}) exited with code {exit_code}. Restarting...")
                    # Close old log file safely
                    try:
                        if name in log_files:
                            log_files[name].close()
                    except Exception:
                        pass
                    start_service(service)
    except KeyboardInterrupt:
        log("Supervisor stopped by KeyboardInterrupt.")
    except Exception as e:
        log(f"[FATAL] Supervisor exception in main loop: {e}")
    finally:
        log("Stopping all monitored services...")
        for name, proc in list(processes.items()):
            try:
                proc.terminate()
                proc.wait(timeout=3)
                log(f"Service {name} (PID {proc.pid}) terminated.")
            except Exception as e:
                log(f"Failed to terminate service {name}: {e}")
        # Close all log files
        for f in log_files.values():
            try:
                f.close()
            except Exception:
                pass
        log("=== SUPERVISOR EXITED ===")

if __name__ == "__main__":
    main()
