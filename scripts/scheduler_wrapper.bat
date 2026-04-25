@echo off
:: SCHEDULER_DISABLED 파일이 있으면 즉시 종료 (자동시작 방지)
if exist "C:\Users\user\Desktop\adscopre\.scheduler_disabled" (
    echo [scheduler] DISABLED flag found. Exiting.
    exit /b 0
)
set PATH=C:\Python314;C:\Python314\Scripts;%PATH%
set PYTHONPATH=C:\Users\user\Desktop\adscopre
cd /d C:\Users\user\Desktop\adscopre
C:\Python314\python.exe scripts\run_scheduler.py
