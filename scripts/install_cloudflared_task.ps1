# AdScope Cloudflared Tunnel - Windows Task Scheduler registration
# Run this script as Administrator

# Remove existing task if any
Unregister-ScheduledTask -TaskName "AdScopeCloudflared" -Confirm:$false -ErrorAction SilentlyContinue

# Create task - run cloudflared tunnel
$action = New-ScheduledTaskAction `
    -Execute "C:\Users\user\Desktop\adscopre\cloudflared.exe" `
    -Argument "tunnel run adscope" `
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
    -TaskName "AdScopeCloudflared" `
    -Action $action `
    -Trigger $trigger1,$trigger2 `
    -Settings $settings `
    -Principal $principal `
    -Description "AdScope Cloudflare Tunnel (adscope.kr)" `
    -Force

Write-Host "AdScopeCloudflared task registered!" -ForegroundColor Green
Read-Host "Press Enter to close"
