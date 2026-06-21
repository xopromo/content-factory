@echo off
cd /d "%~dp0"
echo ==============================================
echo   Starting Jarvis Task Listener Daemon...
echo ==============================================
:loop
python scripts/task_listener.py
echo.
echo [WARN] Task listener exited or crashed. Restarting in 5 seconds...
timeout /t 5 >nul
goto loop
