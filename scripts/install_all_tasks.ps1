# AdScope - Register ALL auto-start tasks
# Run this script as Administrator

Write-Host "=== AdScope Auto-Start Task Registration ===" -ForegroundColor Cyan

# 1. Cloudflared Tunnel
Write-Host "`n[1/3] Registering Cloudflared Tunnel..." -ForegroundColor Yellow
Unregister-ScheduledTask -TaskName "AdScopeCloudflared" -Confirm:$false -ErrorAction SilentlyContinue

$cfAction = New-ScheduledTaskAction `
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
    -Action $cfAction `
    -Trigger $trigger1,$trigger2 `
    -Settings $settings `
    -Principal $principal `
    -Description "AdScope Cloudflare Tunnel (adscope.kr)" `
    -Force | Out-Null

Write-Host "  Cloudflared task registered!" -ForegroundColor Green

# 2. Backend (uvicorn)
Write-Host "`n[2/3] Registering Backend (uvicorn)..." -ForegroundColor Yellow
Unregister-ScheduledTask -TaskName "AdScopeBackend" -Confirm:$false -ErrorAction SilentlyContinue

$beAction = New-ScheduledTaskAction `
    -Execute "C:\Python314\python.exe" `
    -Argument "-m uvicorn api.main:app --host 0.0.0.0 --port 8000" `
    -WorkingDirectory "C:\Users\user\Desktop\adscopre"

Register-ScheduledTask `
    -TaskName "AdScopeBackend" `
    -Action $beAction `
    -Trigger $trigger1,$trigger2 `
    -Settings $settings `
    -Principal $principal `
    -Description "AdScope Backend API (port 8000)" `
    -Force | Out-Null

Write-Host "  Backend task registered!" -ForegroundColor Green

# 3. Frontend (Next.js production)
Write-Host "`n[3/3] Registering Frontend (Next.js)..." -ForegroundColor Yellow
Unregister-ScheduledTask -TaskName "AdScopeFrontend" -Confirm:$false -ErrorAction SilentlyContinue

$feAction = New-ScheduledTaskAction `
    -Execute "cmd.exe" `
    -Argument "/c cd /d C:\Users\user\Desktop\adscopre\frontend && npx next start -p 3001" `
    -WorkingDirectory "C:\Users\user\Desktop\adscopre\frontend"

Register-ScheduledTask `
    -TaskName "AdScopeFrontend" `
    -Action $feAction `
    -Trigger $trigger1,$trigger2 `
    -Settings $settings `
    -Principal $principal `
    -Description "AdScope Frontend (port 3001)" `
    -Force | Out-Null

Write-Host "  Frontend task registered!" -ForegroundColor Green

Write-Host "`n=== All 3 tasks registered! ===" -ForegroundColor Cyan
Write-Host "Tasks: AdScopeCloudflared, AdScopeBackend, AdScopeFrontend" -ForegroundColor White
Write-Host "(+ AdScopeScheduler already registered)" -ForegroundColor Gray
Read-Host "`nPress Enter to close"
