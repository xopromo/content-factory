@echo off
cd /d "%~dp0"
echo ==============================================
echo   Starting Jarvis Headless Services...
echo ==============================================

:: Check if websocket-client is installed
python -c "import websocket" 2>nul || (
    echo Installing websocket-client dependency...
    pip install websocket-client
)

:: Run WebSocket Client in background
echo Starting WebSocket wakeup client...
start /b python -u scripts/websocket_client.py > websocket_client_start.log 2>&1

:: Run main Task Listener (acting as a 10-minute backup check)
echo Starting task listener daemon (10m backup)...
:loop
python scripts/task_listener.py
echo.
echo [WARN] Task listener exited or crashed. Restarting in 5 seconds...
timeout /t 5 >nul
goto loop

