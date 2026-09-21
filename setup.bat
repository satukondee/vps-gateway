@echo off
title AIVANA Sovereign 1-Click Installer
color 0A
echo ===================================================
echo   AIVANA Sovereign MT5 Gateway 1-Click Installer
echo ===================================================
echo.

if not exist "C:\AivanaGateway" mkdir "C:\AivanaGateway"
cd /d "C:\AivanaGateway"

set "PYBIN=python"
python --version >nul 2>&1
if %errorlevel% neq 0 (
    if exist "C:\Program Files\Python311\python.exe" (
        set "PYBIN=C:\Program Files\Python311\python.exe"
        echo [1/5] Found existing Python 3.11 at C:\Program Files\Python311
    ) else (
        echo [1/5] Downloading Python 3.11 64-bit...
        powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://www.python.org/ftp/python/3.11.9/python-3.11.9-amd64.exe' -OutFile '%TEMP%\py_inst.exe'"
        echo [1/5] Installing Python 3.11 silently...
        "%TEMP%\py_inst.exe" /quiet InstallAllUsers=1 PrependPath=1 Include_test=0
        del "%TEMP%\py_inst.exe" /f /q
        set "PATH=C:\Program Files\Python311;C:\Program Files\Python311\Scripts;%PATH%"
        set "PYBIN=C:\Program Files\Python311\python.exe"
    )
) else (
    echo [1/5] Python is already installed and in PATH.
)

echo [2/5] Installing MetaTrader5, FastAPI, and Uvicorn...
"%PYBIN%" -m pip install --upgrade pip
"%PYBIN%" -m pip install MetaTrader5 fastapi uvicorn pydantic

echo [3/5] Downloading AIVANA Gateway Engine...
powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://raw.githubusercontent.com/satukondee/vps-gateway/main/gateway.py' -OutFile 'C:\AivanaGateway\gateway.py'"

echo [4/5] Downloading Cloudflare Tunnel...
if not exist "C:\AivanaGateway\cloudflared.exe" (
    powershell -Command "[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12; Invoke-WebRequest -Uri 'https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-windows-amd64.exe' -OutFile 'C:\AivanaGateway\cloudflared.exe'"
)

echo [5/5] Configuring Windows Firewall...
netsh advfirewall firewall add rule name="AIVANA Gateway 8050" dir=in action=allow protocol=TCP localport=8050 >nul 2>&1

echo Creating Desktop Shortcut...
(
echo @echo off
echo title AIVANA Sovereign Gateway Runner
echo cd /d C:\AivanaGateway
echo start "AIVANA Python Gateway" "%PYBIN%" gateway.py
echo timeout /t 3 /nobreak ^^>nul
echo C:\AivanaGateway\cloudflared.exe tunnel --url http://127.0.0.1:8050 --protocol http2
echo pause
) > "%USERPROFILE%\Desktop\START_AIVANA_GATEWAY.bat"

echo.
echo ===================================================
echo   INSTALLATION COMPLETED! STARTING GATEWAY NOW...
echo ===================================================
echo.
start "AIVANA Python Gateway" "%PYBIN%" gateway.py
timeout /t 3 /nobreak >nul
C:\AivanaGateway\cloudflared.exe tunnel --url http://127.0.0.1:8050 --protocol http2
pause
