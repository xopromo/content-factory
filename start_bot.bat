@echo off
cd /d "%~dp0"
for /f "tokens=1,2 delims==" %%a in (.env) do set %%a=%%b
python scripts/voice_bot.py
pause
