param(
    [string]$Channels = "naver_search,naver_da,naver_shopping,kakao_da",
    [int]$TaskTimeout = 1200,
    [int]$SleepBetween = 10,
    [double]$SkipFreshHours = 0,
    [int]$RestMinutes = 30,
    [int]$DeployDays = 30,
    [switch]$SkipDeploy
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Path $LogDir -Force | Out-Null
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LoopLog = Join-Path $LogDir "live_collection_loop_$Stamp.log"

function Write-LoopLog {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Add-Content -LiteralPath $LoopLog -Value $line -Encoding UTF8
}

function Test-RunningProcessPattern {
    param([string]$Pattern)
    @(Get-CimInstance Win32_Process |
        Where-Object {
            $_.ProcessId -ne $PID -and
            $_.CommandLine -and
            $_.CommandLine -match $Pattern
        }).Count -gt 0
}

function Invoke-LoggedProcess {
    param(
        [string]$Name,
        [string]$FilePath,
        [string[]]$ArgumentList
    )

    $runStamp = Get-Date -Format "yyyyMMdd_HHmmss"
    $outLog = Join-Path $LogDir "$Name`_$runStamp.out.log"
    $errLog = Join-Path $LogDir "$Name`_$runStamp.err.log"

    Write-LoopLog "start $Name out=$outLog err=$errLog"
    $proc = Start-Process `
        -FilePath $FilePath `
        -ArgumentList $ArgumentList `
        -WorkingDirectory $Root `
        -RedirectStandardOutput $outLog `
        -RedirectStandardError $errLog `
        -WindowStyle Hidden `
        -Wait `
        -PassThru

    Write-LoopLog "finish $Name exit=$($proc.ExitCode)"
    if ($proc.ExitCode -ne 0) {
        Write-LoopLog "WARN $Name failed; loop will continue after rest"
    }
    return $proc.ExitCode
}

Write-LoopLog "loop started channels=$Channels task_timeout=$TaskTimeout skip_fresh_hours=$SkipFreshHours rest_minutes=$RestMinutes deploy_days=$DeployDays skip_deploy=$SkipDeploy"

while ($true) {
    try {
        if (Test-RunningProcessPattern "run_live_round_robin.py|sequential_crawl.py") {
            Write-LoopLog "live crawler already running; waiting 60s"
            Start-Sleep -Seconds 60
            continue
        }

        Invoke-LoggedProcess `
            -Name "live_round_robin_loop" `
            -FilePath "C:\Python314\python.exe" `
            -ArgumentList @(
                "scripts\run_live_round_robin.py",
                "--channels", $Channels,
                "--cycles", "1",
                "--task-timeout", "$TaskTimeout",
                "--sleep-between", "$SleepBetween",
                "--skip-fresh-hours", "$SkipFreshHours"
            ) | Out-Null

        if (-not $SkipDeploy) {
            Invoke-LoggedProcess `
                -Name "filter_deploy_loop" `
                -FilePath "C:\Python314\python.exe" `
                -ArgumentList @(
                    "scripts\filter_and_deploy_current.py",
                    "--days", "$DeployDays"
                ) | Out-Null
        }
    }
    catch {
        Write-LoopLog "ERROR $($_.Exception.Message)"
    }

    Write-LoopLog "resting ${RestMinutes}m"
    Start-Sleep -Seconds ($RestMinutes * 60)
}
