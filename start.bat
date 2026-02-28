@echo off
chcp 65001 >nul
title AdScope - Starting Servers

echo ============================================
echo   AdScope Local Server Startup
echo ============================================
echo.

:: API 서버 (SQLite)
echo [1/2] API 서버 시작 (port 8000)...
set DATABASE_URL=sqlite+aiosqlite:///adscope.db
start "AdScope API" cmd /k "cd /d %~dp0 && set DATABASE_URL=sqlite+aiosqlite:///adscope.db && uvicorn api.main:app --host 0.0.0.0 --port 8000"

ping -n 4 127.0.0.1 >nul

:: Frontend 서버
echo [2/2] Frontend 서버 시작 (port 3000)...
start "AdScope Frontend" cmd /k "cd /d %~dp0\frontend && npm run dev"

ping -n 6 127.0.0.1 >nul

echo.
echo ============================================
echo   AdScope 실행 완료
echo   - API:      http://localhost:8000
echo   - Frontend: http://localhost:3000
echo ============================================
echo.

:: 브라우저 자동 열기
start http://localhost:3000
