@echo off
chcp 65001 >nul
cd /d "%~dp0"
title AdScope

echo ========================================
echo   AdScope - Ad Intelligence Platform
echo ========================================

:: DB init (create if missing)
if not exist adscope.db (
    echo [DB] Initializing database...
    python -c "import asyncio; from database import init_db; asyncio.run(init_db())"
    if errorlevel 1 (
        echo [ERROR] DB init failed
        pause
        exit /b 1
    )
    echo [DB] Done
)

:: logs dir
if not exist logs (
    mkdir logs
)

:: Backend API (port 8000)
echo [1/3] Starting API server...
start "AdScope-API" /min cmd /k "cd /d %~dp0 && python -m uvicorn api.main:app --host 0.0.0.0 --port 8000"

ping -n 4 127.0.0.1 >nul

:: Frontend (port 3000)
echo [2/3] Starting frontend...
start "AdScope-Frontend" /min cmd /k "cd /d %~dp0\frontend && npm run dev"

ping -n 6 127.0.0.1 >nul

:: Browser
echo [3/3] Opening browser...
start http://localhost:3000

echo.
echo   API:      http://localhost:8000
echo   Frontend: http://localhost:3000
echo   Docs:     http://localhost:8000/docs
echo ========================================
echo.
echo Press any key to stop all services...
pause >nul

:: Cleanup
taskkill /fi "WINDOWTITLE eq AdScope-API" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq AdScope-Frontend" /f >nul 2>&1
echo Services stopped.
