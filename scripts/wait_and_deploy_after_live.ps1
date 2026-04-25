param(
    [int]$Days = 30,
    [int]$CooldownSeconds = 180
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Log = Join-Path $LogDir "filter_deploy_after_live_$Stamp.log"

function Write-Log {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $Log -Value $line -Encoding UTF8
}

function Get-RunningLiveCrawler {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.ProcessId -ne $PID -and
            $_.CommandLine -and
            ($_.CommandLine -match "run_live_round_robin.py" -or $_.CommandLine -match "sequential_crawl.py")
        }
}

function Get-RunningSocialBoost {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.ProcessId -ne $PID -and
            $_.CommandLine -and
            $_.CommandLine -match "run_social_signal_boost.py"
        }
}

try {
    Write-Log "watcher started days=$Days cooldown_seconds=$CooldownSeconds"
    while (@(Get-RunningLiveCrawler).Count -gt 0) {
        Write-Log "waiting for live crawler to finish"
        Start-Sleep -Seconds 60
    }

    Write-Log "live crawler finished; cooldown for social boost handoff"
    Start-Sleep -Seconds $CooldownSeconds

    while (@(Get-RunningSocialBoost).Count -gt 0) {
        Write-Log "waiting for social signal boost to finish"
        Start-Sleep -Seconds 60
    }

    Write-Log "running filter/deploy"
    Push-Location $Root
    try {
        $RunOut = Join-Path $LogDir "filter_deploy_after_live_$Stamp.run.out.log"
        $RunErr = Join-Path $LogDir "filter_deploy_after_live_$Stamp.run.err.log"
        $Proc = Start-Process `
            -FilePath "C:\Python314\python.exe" `
            -ArgumentList @("scripts\filter_and_deploy_current.py", "--days", "$Days") `
            -WorkingDirectory $Root `
            -RedirectStandardOutput $RunOut `
            -RedirectStandardError $RunErr `
            -WindowStyle Hidden `
            -Wait `
            -PassThru
        if (Test-Path -LiteralPath $RunOut) {
            Get-Content -LiteralPath $RunOut -Encoding UTF8 |
                ForEach-Object { Add-Content -LiteralPath $Log -Value $_ -Encoding UTF8 }
        }
        if (Test-Path -LiteralPath $RunErr) {
            Get-Content -LiteralPath $RunErr -Encoding UTF8 |
                ForEach-Object { Add-Content -LiteralPath $Log -Value $_ -Encoding UTF8 }
        }
        if ($Proc.ExitCode -ne 0) {
            throw "filter/deploy exited with code $($Proc.ExitCode)"
        }
    }
    finally {
        Pop-Location
    }
    Write-Log "filter/deploy complete"
}
catch {
    Write-Log "ERROR: $($_.Exception.Message)"
    exit 1
}
