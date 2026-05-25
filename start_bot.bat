@echo off
cd /d C:\Users\асус\content-factory
for /f "tokens=1,2 delims==" %%a in (.env) do set %%a=%%b
python scripts/voice_bot.py
pause
