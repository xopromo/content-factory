@echo off
cd /d "%~dp0"
:loop
python -u scripts/websocket_client.py >> websocket_client_start.log 2>&1
echo [WARN] WebSocket client exited or crashed. Restarting in 5 seconds...
ping -n 6 127.0.0.1 >nul
goto loop
