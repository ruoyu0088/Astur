@echo off
rem Astur launcher for this checkout: double-click to run the window manager.
setlocal
cd /d "%~dp0"

set "EXE=target\release\astur.exe"
if not exist "%EXE%" set "EXE=target\debug\astur.exe"
if not exist "%EXE%" (
    echo No astur.exe yet, building the release build (this takes a while)...
    cargo build --release -p astur
    if errorlevel 1 goto failed
    set "EXE=target\release\astur.exe"
)

echo Starting %EXE%
start "Astur" "%EXE%"
exit /b 0

:failed
echo.
echo Build failed, see the messages above.
pause
exit /b 1