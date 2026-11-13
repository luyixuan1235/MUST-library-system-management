@echo off
chcp 65001 >nul
title Library Seat Management System Launcher
set "PROJECT_ROOT=%~dp0"
set "BACKEND_DIR=%PROJECT_ROOT%BACKEND"
set "APP_EXE=C:\Users\luyixuan\LibrarySeatApp\flutter_application_1.exe"
set "APP_SRC=%PROJECT_ROOT%FRONTEND\build\windows\x64\runner\Release"

echo ========================================================
echo   Library Seat Management System (Desktop + Wi-Fi Hub)
echo ========================================================

:: Check if backend port 8000 is already listening
netstat -ano | findstr ":8000 " | findstr "LISTENING" >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo [1/3] Starting FastAPI Backend Server on 0.0.0.0:8000 ...
    start "LibrarySeat Backend (0.0.0.0:8000)" /min cmd /c "cd /d "%BACKEND_DIR%" && C:\miniconda3\python.exe -m uvicorn backend.main:app --host 0.0.0.0 --port 8000"
    timeout /t 3 /nobreak >nul
) else (
    echo [1/3] Backend server is already running on port 8000.
)

:: Detect LAN IP for Wi-Fi sharing
for /f "delims=" %%i in ('C:\miniconda3\python.exe -c "import socket; s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM); s.connect(('8.8.8.8',80)); print(s.getsockname()[0]); s.close()" 2^>nul') do set "LAN_IP=%%i"
if "%LAN_IP%"=="" set "LAN_IP=127.0.0.1"

echo [2/3] Same-WiFi Share ^& Download Portal:
echo       http://%LAN_IP%:8000/download
echo       Web App Online (Mobile/PC):
echo       http://%LAN_IP%:8000/app/

:: Keep the ASCII-path copy in sync with the latest build.
:: Flutter Windows crashes on non-ASCII (Chinese) install paths, so we always
:: run from C:\Users\luyixuan\LibrarySeatApp instead of the project folder.
if exist "%APP_SRC%\flutter_application_1.exe" (
    robocopy "%APP_SRC%" "C:\Users\luyixuan\LibrarySeatApp" /MIR /NFL /NDL /NJH /NJS /NP >nul
)

:: Launch native Windows Desktop App
if exist "%APP_EXE%" (
    echo [3/3] Launching Windows Desktop App...
    start "" "%APP_EXE%"
) else (
    echo [3/3] Opening Web App in browser...
    start "" "http://%LAN_IP%:8000/app/"
)

:: Also open the Wi-Fi Download Portal so you can share the link with classmates
start "" "http://%LAN_IP%:8000/download"
exit /b 0
