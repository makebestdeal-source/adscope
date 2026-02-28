@echo off
REM ============================================================
REM AdScope Scheduler - NSSM Windows Service Installer
REM Service name: AdScopeScheduler
REM
REM Requirements:
REM   nssm.exe at C:\nssm\nssm.exe  OR  in PATH
REM   Download: https://nssm.cc/download
REM   Chocolatey: choco install nssm
REM
REM Usage:
REM   install_scheduler_service.bat          -- install service
REM   install_scheduler_service.bat remove   -- uninstall service
REM ============================================================

setlocal EnableDelayedExpansion

REM ---- Resolve project root (parent of scripts\) ----
set "PROJECT_DIR=%~dp0.."
pushd "%PROJECT_DIR%"
set "PROJECT_DIR=%CD%"
popd

set "SERVICE_NAME=AdScopeScheduler"
set "LOG_DIR=%PROJECT_DIR%\logs"
set "STDOUT_LOG=%LOG_DIR%\scheduler_service.log"
set "STDERR_LOG=%LOG_DIR%\scheduler_service_err.log"

REM ---- Locate nssm.exe ----
set "NSSM="
if exist "C:\nssm\nssm.exe"      set "NSSM=C:\nssm\nssm.exe"
if exist "C:\nssm\win64\nssm.exe" set "NSSM=C:\nssm\win64\nssm.exe"
if exist "C:\tools\nssm\nssm.exe" set "NSSM=C:\tools\nssm\nssm.exe"
if "!NSSM!"=="" (
    where nssm >nul 2>&1
    if !ERRORLEVEL! EQU 0 set "NSSM=nssm"
)

REM ---- Locate python.exe ----
set "PYTHON_EXE="
for /f "tokens=*" %%i in ('where python 2^>nul') do (
    if "!PYTHON_EXE!"=="" set "PYTHON_EXE=%%i"
)
if "!PYTHON_EXE!"=="" (
    echo [ERROR] python.exe not found in PATH.
    echo         Activate your virtual environment or add Python to PATH.
    goto :eof_error
)

REM ================================================================
REM  REMOVE mode
REM ================================================================
if /i "%~1"=="remove" goto :remove_service

REM ================================================================
REM  INSTALL mode (default)
REM ================================================================
echo.
echo ============================================================
echo  AdScope Scheduler Service Installer
echo ============================================================
echo  Service  : %SERVICE_NAME%
echo  Project  : %PROJECT_DIR%
echo  Python   : %PYTHON_EXE%
echo  Stdout   : %STDOUT_LOG%
echo  Stderr   : %STDERR_LOG%
echo ============================================================
echo.

REM ---- nssm not found ----
if "!NSSM!"=="" (
    echo [ERROR] nssm.exe not found.
    echo.
    echo  Manual installation options:
    echo    1. Chocolatey (recommended, run as Admin):
    echo         choco install nssm
    echo.
    echo    2. Download manually:
    echo         https://nssm.cc/download
    echo         Extract nssm.exe to C:\nssm\  or any folder in PATH.
    echo.
    echo    3. After installing nssm, re-run this script as Administrator.
    echo.
    echo  Manual service creation (without nssm):
    echo    sc create %SERVICE_NAME% ^
    echo       binPath= "\"!PYTHON_EXE!\" \"%PROJECT_DIR%\scripts\run_scheduler.py\""
    echo    sc description %SERVICE_NAME% "AdScope Scheduler - Automated ad crawling service"
    echo    sc config %SERVICE_NAME% start= auto
    echo.
    goto :eof_error
)

REM ---- Create log directory ----
if not exist "%LOG_DIR%" (
    mkdir "%LOG_DIR%"
    echo [INFO] Created log directory: %LOG_DIR%
)

REM ---- Check for existing service and stop it ----
sc query "%SERVICE_NAME%" >nul 2>&1
if !ERRORLEVEL! EQU 0 (
    echo [INFO] Service '%SERVICE_NAME%' already exists. Stopping and removing first...
    "!NSSM!" stop "%SERVICE_NAME%" >nul 2>&1
    timeout /t 3 /nobreak >nul
    "!NSSM!" remove "%SERVICE_NAME%" confirm
    timeout /t 2 /nobreak >nul
)

REM ---- Install service ----
echo [1/9] Installing service '%SERVICE_NAME%'...
"!NSSM!" install "%SERVICE_NAME%" "!PYTHON_EXE!" "scripts\run_scheduler.py"
if !ERRORLEVEL! NEQ 0 (
    echo [ERROR] nssm install failed. Make sure you are running as Administrator.
    goto :eof_error
)

echo [2/9] Setting AppDirectory...
"!NSSM!" set "%SERVICE_NAME%" AppDirectory "%PROJECT_DIR%"

echo [3/9] Setting AppParameters...
"!NSSM!" set "%SERVICE_NAME%" AppParameters "scripts\run_scheduler.py"

echo [4/9] Setting stdout log...
"!NSSM!" set "%SERVICE_NAME%" AppStdout "%STDOUT_LOG%"

echo [5/9] Setting stderr log...
"!NSSM!" set "%SERVICE_NAME%" AppStderr "%STDERR_LOG%"

echo [6/9] Enabling log rotation...
"!NSSM!" set "%SERVICE_NAME%" AppRotateFiles 1
"!NSSM!" set "%SERVICE_NAME%" AppRotateBytes 10485760

echo [7/9] Setting start type to AUTO...
"!NSSM!" set "%SERVICE_NAME%" Start SERVICE_AUTO_START

echo [8/9] Setting description...
"!NSSM!" set "%SERVICE_NAME%" Description "AdScope Scheduler - Automated ad crawling service"

echo [9/9] Setting restart delay (10s on crash)...
"!NSSM!" set "%SERVICE_NAME%" AppRestartDelay 10000

echo.
echo ============================================================
echo  Service '%SERVICE_NAME%' installed successfully.
echo ============================================================
echo.
echo  Commands:
echo    Start   :  nssm start %SERVICE_NAME%
echo    Stop    :  nssm stop %SERVICE_NAME%
echo    Restart :  nssm restart %SERVICE_NAME%
echo    Status  :  nssm status %SERVICE_NAME%
echo    Edit    :  nssm edit %SERVICE_NAME%
echo    Remove  :  %~nx0 remove
echo.
echo  Logs:
echo    Stdout  :  %STDOUT_LOG%
echo    Stderr  :  %STDERR_LOG%
echo    App log :  %PROJECT_DIR%\logs\scheduler_YYYY-MM-DD.log
echo.

set /p START_NOW="Start the service now? (Y/N): "
if /i "!START_NOW!"=="Y" (
    echo Starting %SERVICE_NAME%...
    "!NSSM!" start "%SERVICE_NAME%"
    timeout /t 3 /nobreak >nul
    "!NSSM!" status "%SERVICE_NAME%"
)

goto :eof_ok

REM ================================================================
REM  REMOVE / UNINSTALL
REM ================================================================
:remove_service
echo.
echo ============================================================
echo  Removing service '%SERVICE_NAME%'
echo ============================================================
echo.

if "!NSSM!"=="" (
    echo [ERROR] nssm.exe not found. Cannot remove service automatically.
    echo.
    echo  Manual removal:
    echo    sc stop %SERVICE_NAME%
    echo    sc delete %SERVICE_NAME%
    echo.
    goto :eof_error
)

sc query "%SERVICE_NAME%" >nul 2>&1
if !ERRORLEVEL! NEQ 0 (
    echo [INFO] Service '%SERVICE_NAME%' is not currently installed.
    goto :eof_ok
)

echo [1/3] Stopping service...
"!NSSM!" stop "%SERVICE_NAME%"
timeout /t 5 /nobreak >nul

echo [2/3] Removing service...
"!NSSM!" remove "%SERVICE_NAME%" confirm
if !ERRORLEVEL! NEQ 0 (
    echo [ERROR] Failed to remove service. Make sure you are running as Administrator.
    goto :eof_error
)

echo [3/3] Done.
echo.
echo  Service '%SERVICE_NAME%' has been removed.
echo  Log files are preserved at: %LOG_DIR%
echo.
goto :eof_ok

:eof_error
echo.
echo [FAILED] Script encountered an error. See messages above.
echo.
endlocal
pause
exit /b 1

:eof_ok
endlocal
pause
exit /b 0
