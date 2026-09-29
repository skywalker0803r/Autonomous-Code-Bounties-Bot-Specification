@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0"

if not exist ".env" (
    echo [Bounty Bot] Creating .env from .env.example ...
    copy /y ".env.example" ".env" >nul
)

echo [Bounty Bot] Checking Docker Desktop (needed for the sandbox test stage) ...
docker info >nul 2>&1
if errorlevel 1 (
    set "DOCKER_DESKTOP_EXE="
    if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" (
        set "DOCKER_DESKTOP_EXE=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
    ) else if exist "%LocalAppData%\Programs\DockerDesktop\Docker Desktop.exe" (
        set "DOCKER_DESKTOP_EXE=%LocalAppData%\Programs\DockerDesktop\Docker Desktop.exe"
    )
    if defined DOCKER_DESKTOP_EXE (
        echo [Bounty Bot] Docker engine not running - starting Docker Desktop in the background ...
        start "" "!DOCKER_DESKTOP_EXE!"
    ) else (
        echo [Bounty Bot] Docker Desktop not found in the usual install locations.
        echo [Bounty Bot] The sandbox test stage will fail until you start it manually.
    )
) else (
    echo [Bounty Bot] Docker engine already running.
)

if not exist "webapp\frontend\dist\index.html" (
    echo [Bounty Bot] No frontend build found.
    echo [Bounty Bot] Run this once from webapp\frontend to build it:
    echo.
    echo     cd webapp\frontend
    echo     npm install
    echo     npm run build
    echo.
    pause
    exit /b 1
)

echo [Bounty Bot] Starting server ...
rem Bind 0.0.0.0, not just localhost, so a phone on the same Wi-Fi can open
rem the same web app (e.g. to install it as a PWA / "Add to Home Screen").
start "Bounty Bot Server" cmd /k python -m uvicorn webapp.backend.app:app --host 0.0.0.0 --port 8000

echo [Bounty Bot] Waiting for server to come up ...
timeout /t 3 /nobreak >nul

start "" http://localhost:8000

echo [Bounty Bot] Opened http://localhost:8000 in your browser.
echo [Bounty Bot] Closing this window will NOT stop the server -
echo [Bounty Bot] close the "Bounty Bot Server" window to stop it.

set "LAN_IP="
for /f "delims=" %%a in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' -and $_.InterfaceAlias -notmatch 'WSL|Loopback|vEthernet' } | Select-Object -First 1 -ExpandProperty IPAddress)" 2^>nul') do set "LAN_IP=%%a"
if defined LAN_IP (
    echo.
    echo [Bounty Bot] On your phone, on the same Wi-Fi, open:
    echo     http://%LAN_IP%:8000
    echo [Bounty Bot] Then use the browser menu to "Add to Home Screen" for an app-like icon.
)

endlocal

