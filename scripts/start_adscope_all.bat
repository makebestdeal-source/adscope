@echo off
title AdScope Services Startup
cd /d C:\Users\user\Desktop\adscopre

echo === Starting AdScope Services ===

:: 1. Start Cloudflared Tunnel
echo [1/4] Starting Cloudflare Tunnel...
start /B "" cloudflared.exe tunnel run adscope > logs\cloudflared.log 2>&1

:: Wait for tunnel
timeout /t 3 /nobreak > nul

:: 2. Start Backend (uvicorn)
echo [2/4] Starting Backend API (port 8000)...
start /B "" C:\Python314\python.exe -m uvicorn api.main:app --host 0.0.0.0 --port 8000 > logs\uvicorn.log 2>&1

:: Wait for backend
timeout /t 3 /nobreak > nul

:: 3. Start Frontend (Next.js production)
echo [3/4] Starting Frontend (port 3001)...
cd frontend
start /B "" cmd /c "npx next start -p 3001 > ..\logs\frontend.log 2>&1"
cd ..

:: 4. Start Scheduler
echo [4/4] Starting Scheduler...
start /B "" C:\Python314\python.exe scripts\run_scheduler.py > logs\scheduler.log 2>&1

echo.
echo === All services started! ===
echo   Cloudflared Tunnel: adscope.kr
echo   Backend API: localhost:8000
echo   Frontend: localhost:3001
echo   Scheduler: running
echo.
echo This window will minimize. Do NOT close it.
timeout /t 5 /nobreak > nul
