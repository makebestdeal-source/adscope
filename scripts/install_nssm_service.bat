@echo off
echo === AdScope Scheduler Service Install ===
cd /d C:\Users\user\Desktop\adscopre

:: Remove existing service if any
nssm.exe stop AdScopeScheduler >nul 2>&1
nssm.exe remove AdScopeScheduler confirm >nul 2>&1

:: Install scheduler service using wrapper bat
nssm.exe install AdScopeScheduler "C:\Users\user\Desktop\adscopre\scripts\scheduler_wrapper.bat"
nssm.exe set AdScopeScheduler AppDirectory "C:\Users\user\Desktop\adscopre"
nssm.exe set AdScopeScheduler DisplayName "AdScope Scheduler"
nssm.exe set AdScopeScheduler Description "AdScope automated ad collection scheduler"
nssm.exe set AdScopeScheduler Start SERVICE_AUTO_START
nssm.exe set AdScopeScheduler AppStdout "C:\Users\user\Desktop\adscopre\logs\scheduler_service.log"
nssm.exe set AdScopeScheduler AppStderr "C:\Users\user\Desktop\adscopre\logs\scheduler_service.log"
nssm.exe set AdScopeScheduler AppRotateFiles 1
nssm.exe set AdScopeScheduler AppRotateBytes 10485760

:: Start the service
nssm.exe start AdScopeScheduler

echo === Done! ===
pause
