@echo off
cd /d "%~dp0"
set STARTUP_DIR=%APPDATA%\Microsoft\Windows\Start Menu\Programs\Startup
set VBS_PATH=%cd%\run_invisible.vbs

echo Creating startup shortcut...
echo Set oWS = WScript.CreateObject("WScript.Shell") > "%temp%\create_shortcut.vbs"
echo sLinkFile = "%STARTUP_DIR%\JarvisTaskListener.lnk" >> "%temp%\create_shortcut.vbs"
echo Set oLink = oWS.CreateShortcut(sLinkFile) >> "%temp%\create_shortcut.vbs"
echo oLink.TargetPath = "wscript.exe" >> "%temp%\create_shortcut.vbs"
echo oLink.Arguments = """%VBS_PATH%""" >> "%temp%\create_shortcut.vbs"
echo oLink.WorkingDirectory = "%cd%" >> "%temp%\create_shortcut.vbs"
echo oLink.Save >> "%temp%\create_shortcut.vbs"

cscript /nologo "%temp%\create_shortcut.vbs"
del "%temp%\create_shortcut.vbs"

echo ==============================================================
echo [SUCCESS] Jarvis Task Listener has been added to Startup!
echo It will now run silently in the background when Windows starts.
echo ==============================================================
echo To run it immediately in the background, double-click run_invisible.vbs.
echo To stop it, close it from Task Manager (kill "python.exe" / "wscript.exe" processes).
echo ==============================================================
pause
