@echo off
chcp 65001 >nul
echo ========================================
echo  AdScope - INVENTOR Integrated Runner
echo  API: 8000 / Frontend: 3000
echo ========================================

:: ── 1. 포트 잔존 프로세스 정리 ──
echo [CLEANUP] Checking ports...
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":8000 " ^| findstr "LISTENING"') do (
    if not "%%p"=="0" (
        taskkill /PID %%p /T /F >nul 2>&1
    )
)
for /f "tokens=5" %%p in ('netstat -ano ^| findstr ":3000 " ^| findstr "LISTENING"') do (
    if not "%%p"=="0" (
        taskkill /PID %%p /T /F >nul 2>&1
    )
)
echo [CLEANUP] Done.

:: ── 2. Backend API (port 8000) ──
echo [START] API server (port 8000)...
cd /d %~dp0
start /b "" python -m uvicorn api.main:app --host 0.0.0.0 --port 8000
ping -n 4 127.0.0.1 >nul

:: ── 3. Frontend (Next.js port 3000) ──
echo [START] Frontend (port 3000)...
cd /d %~dp0frontend
start /b "" cmd /c "npm run dev"
ping -n 3 127.0.0.1 >nul

echo.
echo [READY] API:      http://localhost:8000
echo [READY] Frontend: http://localhost:3000

:: ── 4. 무한 대기 ──
:loop
ping -n 60 127.0.0.1 >nul
goto loop
