@echo off
REM ============================================
REM AdScope Windows Service Installer (NSSM)
REM ============================================
REM Prerequisites: Install NSSM (https://nssm.cc)
REM   choco install nssm  OR  download from nssm.cc
REM ============================================

setlocal

set PROJECT_DIR=%~dp0..
set PYTHON=python
set LOG_DIR=%PROJECT_DIR%\logs

REM Create log directory
if not exist "%LOG_DIR%" mkdir "%LOG_DIR%"

echo.
echo === AdScope Service Installer ===
echo Project: %PROJECT_DIR%
echo.

REM 1. Backend API
echo [1/3] Installing AdScope-API service...
nssm install AdScope-API "%PYTHON%" -m uvicorn api.main:app --host 0.0.0.0 --port 8000
nssm set AdScope-API AppDirectory "%PROJECT_DIR%"
nssm set AdScope-API AppStdout "%LOG_DIR%\api_stdout.log"
nssm set AdScope-API AppStderr "%LOG_DIR%\api_stderr.log"
nssm set AdScope-API AppRotateFiles 1
nssm set AdScope-API AppRotateBytes 10485760
nssm set AdScope-API AppRestartDelay 5000
nssm set AdScope-API Description "AdScope FastAPI Backend"
echo Done.

REM 2. Scheduler
echo [2/3] Installing AdScope-Scheduler service...
nssm install AdScope-Scheduler "%PYTHON%" scripts/run_scheduler.py
nssm set AdScope-Scheduler AppDirectory "%PROJECT_DIR%"
nssm set AdScope-Scheduler AppStdout "%LOG_DIR%\scheduler_stdout.log"
nssm set AdScope-Scheduler AppStderr "%LOG_DIR%\scheduler_stderr.log"
nssm set AdScope-Scheduler AppRotateFiles 1
nssm set AdScope-Scheduler AppRotateBytes 10485760
nssm set AdScope-Scheduler AppRestartDelay 10000
nssm set AdScope-Scheduler Description "AdScope Crawl Scheduler"
echo Done.

REM 3. Frontend
echo [3/3] Installing AdScope-Frontend service...
nssm install AdScope-Frontend cmd /c "cd /d %PROJECT_DIR%\frontend && npx next start -p 3001"
nssm set AdScope-Frontend AppDirectory "%PROJECT_DIR%\frontend"
nssm set AdScope-Frontend AppStdout "%LOG_DIR%\frontend_stdout.log"
nssm set AdScope-Frontend AppStderr "%LOG_DIR%\frontend_stderr.log"
nssm set AdScope-Frontend AppRotateFiles 1
nssm set AdScope-Frontend AppRotateBytes 10485760
nssm set AdScope-Frontend Description "AdScope Next.js Frontend"
echo Done.

echo.
echo === All services installed ===
echo.
echo To start all services:
echo   nssm start AdScope-API
echo   nssm start AdScope-Scheduler
echo   nssm start AdScope-Frontend
echo.
echo To check status:
echo   nssm status AdScope-API
echo   nssm status AdScope-Scheduler
echo   nssm status AdScope-Frontend
echo.
echo To remove services:
echo   nssm remove AdScope-API confirm
echo   nssm remove AdScope-Scheduler confirm
echo   nssm remove AdScope-Frontend confirm
echo.

endlocal
pause
