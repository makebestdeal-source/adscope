@echo off
setlocal EnableExtensions
cd /d "%~dp0frontend"

if not exist "package.json" (
  echo [AdScope] frontend\package.json not found.
  exit /b 1
)

where npm >nul 2>&1
if errorlevel 1 (
  echo [AdScope] npm is required but was not found in PATH.
  exit /b 1
)

if not exist "node_modules" (
  echo [AdScope] Installing frontend dependencies...
  call npm install
  if errorlevel 1 exit /b %errorlevel%
)

echo [AdScope] Starting frontend on http://localhost:3000
call npm run dev
exit /b %errorlevel%
