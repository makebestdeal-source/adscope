@echo off
setlocal EnableExtensions EnableDelayedExpansion
cd /d "%~dp0"

set "PYTHON=python"
if exist ".venv\Scripts\python.exe" set "PYTHON=.venv\Scripts\python.exe"
set "DEFAULT_SQLITE_URL=sqlite+aiosqlite:///adscope.db"

if exist ".env" (
  for /f "usebackq tokens=* delims=" %%L in (".env") do (
    set "LINE=%%L"
    if not "!LINE!"=="" if not "!LINE:~0,1!"=="#" (
      for /f "tokens=1,* delims==" %%A in ("!LINE!") do (
        set "KEY=%%~A"
        set "VAL=%%~B"
        if not "!KEY!"=="" set "!KEY!=!VAL!"
      )
    )
  )
)

if /I "%BACKEND_USE_ENV_DB%"=="1" (
  if "%DATABASE_URL%"=="" set "DATABASE_URL=%DEFAULT_SQLITE_URL%"
) else (
  if not "%DATABASE_URL%"=="" if /I not "%DATABASE_URL%"=="%DEFAULT_SQLITE_URL%" (
    echo [AdScope] BACKEND_USE_ENV_DB is not set. Using SQLite for local run.
    echo [AdScope] Set BACKEND_USE_ENV_DB=1 to use DATABASE_URL from .env
  )
  set "DATABASE_URL=%DEFAULT_SQLITE_URL%"
)

echo [AdScope] Starting backend on http://localhost:8000
echo [AdScope] DATABASE_URL=!DATABASE_URL!
call "%PYTHON%" -m uvicorn api.main:app --host 0.0.0.0 --port 8000 --reload
exit /b %errorlevel%
