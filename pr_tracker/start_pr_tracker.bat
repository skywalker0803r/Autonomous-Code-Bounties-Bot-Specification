@echo off
setlocal EnableDelayedExpansion

cd /d "%~dp0\.."

echo [PR Tracker] Starting standalone PR tracker (independent of the main Bounty Bot server) ...
start "Bounty Bot PR Tracker" cmd /k python -m uvicorn pr_tracker.server:app --host 0.0.0.0 --port 8010

echo [PR Tracker] Waiting for server to come up ...
timeout /t 2 /nobreak >nul

set "LAN_IP="
for /f "delims=" %%a in ('powershell -NoProfile -Command "(Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '169.254.*' -and $_.IPAddress -ne '127.0.0.1' -and $_.InterfaceAlias -notmatch 'WSL|Loopback|vEthernet' } | Select-Object -First 1 -ExpandProperty IPAddress)" 2^>nul') do set "LAN_IP=%%a"

start "" http://localhost:8010

echo.
echo [PR Tracker] Opened http://localhost:8010 on this PC.
if defined LAN_IP (
    echo [PR Tracker] On your phone, on the same Wi-Fi, open:
    echo     http://%LAN_IP%:8010
    echo [PR Tracker] Then use the browser menu to "Add to Home Screen" for an app-like icon.
)
echo [PR Tracker] Closing this window will NOT stop the server -
echo [PR Tracker] close the "Bounty Bot PR Tracker" window to stop it.

endlocal
