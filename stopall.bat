@echo off
echo Stopping AdScope services...
taskkill /fi "WINDOWTITLE eq AdScope-API" /f >nul 2>&1
taskkill /fi "WINDOWTITLE eq AdScope-Frontend" /f >nul 2>&1
echo All services stopped.
pause
