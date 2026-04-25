param(
    [int]$IntervalHours = 12,
    [int]$MaxRuns = 0,
    [switch]$WaitForLiveCrawler,
    [int]$DiscoverLimit = 500,
    [int]$ContentLimit = 80,
    [int]$StatsLimit = 120,
    [int]$NewsLimit = 150,
    [int]$TrendLimit = 100,
    [int]$PerChannelTimeoutSeconds = 45
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$LoopStamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LoopLog = Join-Path $LogDir "social_signal_boost_loop_$LoopStamp.log"
$MetaFile = Join-Path $LogDir "social_signal_boost_loop_$LoopStamp.meta.json"

$env:PYTHONIOENCODING = "utf-8"
$runCount = 0
$startedAt = Get-Date

function Write-LoopLog {
    param([string]$Message)
    "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] $Message" |
        Add-Content -Encoding utf8 -Path $LoopLog
}

function Get-LiveCrawlerProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -match "run_live_round_robin|sequential_crawl.py"
        }
}

function Get-SocialBoostProcesses {
    Get-CimInstance Win32_Process |
        Where-Object {
            $_.CommandLine -match "run_social_signal_boost.py"
        }
}

function Write-Meta {
    param([string]$Status, [int]$Runs)
    $meta = [ordered]@{
        started_at = $startedAt.ToString("s")
        updated_at = (Get-Date).ToString("s")
        status = $Status
        interval_hours = $IntervalHours
        max_runs = $MaxRuns
        completed_runs = $Runs
        wait_for_live_crawler = [bool]$WaitForLiveCrawler
        loop_log = $LoopLog
    }
    $meta | ConvertTo-Json | Set-Content -Encoding utf8 -Path $MetaFile
}

Write-LoopLog "social signal boost loop started"
Write-Meta -Status "running" -Runs 0

while ($true) {
    if ($MaxRuns -gt 0 -and $runCount -ge $MaxRuns) {
        Write-LoopLog "max runs reached: $MaxRuns"
        Write-Meta -Status "completed" -Runs $runCount
        break
    }

    if ($WaitForLiveCrawler) {
        while (Get-LiveCrawlerProcesses) {
            Write-LoopLog "waiting for live crawler to finish"
            Start-Sleep -Seconds 60
        }
    }

    $existingBoost = @(Get-SocialBoostProcesses)
    if ($existingBoost.Count -gt 0) {
        Write-LoopLog "social boost already running; skipping this slot"
    } else {
        $Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
        $OutLog = Join-Path $LogDir "social_signal_boost_$Stamp.out.log"
        $ErrLog = Join-Path $LogDir "social_signal_boost_$Stamp.err.log"

        $argsList = @(
            "scripts\run_social_signal_boost.py",
            "--discover-limit", "$DiscoverLimit",
            "--content-limit", "$ContentLimit",
            "--stats-limit", "$StatsLimit",
            "--news-limit", "$NewsLimit",
            "--trend-limit", "$TrendLimit",
            "--per-channel-timeout", "$PerChannelTimeoutSeconds"
        )

        Write-LoopLog "starting social boost run $($runCount + 1)"
        $proc = Start-Process -FilePath "C:\Python314\python.exe" `
            -ArgumentList $argsList `
            -WorkingDirectory $Root `
            -RedirectStandardOutput $OutLog `
            -RedirectStandardError $ErrLog `
            -WindowStyle Hidden `
            -PassThru

        Write-LoopLog "started pid $($proc.Id), out=$OutLog, err=$ErrLog"
        Wait-Process -Id $proc.Id
        $proc.Refresh()
        $runCount += 1
        Write-LoopLog "run $runCount finished with exit code $($proc.ExitCode)"
        Write-Meta -Status "running" -Runs $runCount
    }

    if ($MaxRuns -gt 0 -and $runCount -ge $MaxRuns) {
        Write-LoopLog "max runs reached after run: $MaxRuns"
        Write-Meta -Status "completed" -Runs $runCount
        break
    }

    $sleepSeconds = [Math]::Max(1, $IntervalHours) * 3600
    Write-LoopLog "sleeping $IntervalHours hour(s)"
    Start-Sleep -Seconds $sleepSeconds
}
