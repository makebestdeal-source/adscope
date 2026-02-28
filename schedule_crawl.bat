@echo off
chcp 65001 >nul
cd /d "%~dp0"

:: Ensure logs directory exists
if not exist logs (
    mkdir logs
)

echo [%date% %time%] Starting daily crawl...
python scripts/fast_crawl.py >> logs/crawl_%date:~0,4%%date:~5,2%%date:~8,2%.log 2>&1
echo [%date% %time%] Daily crawl completed.
