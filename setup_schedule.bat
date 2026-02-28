@echo off
echo Registering AdScope daily crawl task...
schtasks /create /tn "AdScope-DailyCrawl" /tr "%~dp0schedule_crawl.bat" /sc daily /st 06:00 /f
echo.
echo Task registered: AdScope-DailyCrawl (daily at 06:00)
echo.
echo To check: schtasks /query /tn "AdScope-DailyCrawl"
echo To remove: schtasks /delete /tn "AdScope-DailyCrawl" /f
pause
