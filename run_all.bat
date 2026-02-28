@echo off
setlocal EnableExtensions
cd /d "%~dp0"

start "AdScope Backend" cmd /k call "%~dp0run_backend.bat"
start "AdScope Frontend" cmd /k call "%~dp0run_frontend.bat"

echo [AdScope] Waiting for servers to start...
ping -n 6 127.0.0.1 >nul
echo [AdScope] Opening browser at http://localhost:3000
start "" "http://localhost:3000"
