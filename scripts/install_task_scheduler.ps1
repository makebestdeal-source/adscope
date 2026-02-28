# AdScope Scheduler - Windows Task Scheduler registration
# Run this script as Administrator

# Remove nssm service if exists
$nssmPath = "C:\Users\user\Desktop\adscopre\nssm.exe"
if (Test-Path $nssmPath) {
    & $nssmPath stop AdScopeScheduler 2>$null
    & $nssmPath remove AdScopeScheduler confirm 2>$null
}

# Remove existing task if any
Unregister-ScheduledTask -TaskName "AdScopeScheduler" -Confirm:$false -ErrorAction SilentlyContinue

# Create task
$action = New-ScheduledTaskAction `
    -Execute "C:\Python314\python.exe" `
    -Argument "scripts\run_scheduler.py" `
    -WorkingDirectory "C:\Users\user\Desktop\adscopre"

$trigger1 = New-ScheduledTaskTrigger -AtLogon
$trigger2 = New-ScheduledTaskTrigger -AtStartup

$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 1) `
    -ExecutionTimeLimit (New-TimeSpan -Days 365)

$principal = New-ScheduledTaskPrincipal -UserId "$env:USERNAME" -LogonType Interactive -RunLevel Highest

Register-ScheduledTask `
    -TaskName "AdScopeScheduler" `
    -Action $action `
    -Trigger $trigger1,$trigger2 `
    -Settings $settings `
    -Principal $principal `
    -Description "AdScope automated ad collection scheduler" `
    -Force

Start-ScheduledTask -TaskName "AdScopeScheduler"
Write-Host "AdScopeScheduler task registered and started!" -ForegroundColor Green
Read-Host "Press Enter to close"
