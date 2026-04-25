param(
    [int]$Hours = 12,
    [string]$Months = "2025-01,2025-02,2025-03,2025-04",
    [string]$Channels = "search,gdn,yt",
    [int]$Cycles = 4,
    [int]$BatchSize = 3,
    [int]$TaskTimeoutSeconds = 1800
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..")
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogDir = Join-Path $Root "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null

$OutLog = Join-Path $LogDir "archive_12h_boost_$Stamp.out.log"
$ErrLog = Join-Path $LogDir "archive_12h_boost_$Stamp.err.log"
$PidFile = Join-Path $LogDir "archive_12h_boost_$Stamp.pid"
$MetaFile = Join-Path $LogDir "archive_12h_boost_$Stamp.meta.json"

$env:PYTHONIOENCODING = "utf-8"
$argsList = @(
    "scripts\run_archive_round_robin.py",
    "--months", $Months,
    "--channels", $Channels,
    "--cycles", "$Cycles",
    "--batch-size", "$BatchSize",
    "--timeout", "$TaskTimeoutSeconds",
    "--include-all-prefixes",
    "--skip-completed"
)

$startedAt = Get-Date
$proc = Start-Process -FilePath "python" `
    -ArgumentList $argsList `
    -WorkingDirectory $Root `
    -RedirectStandardOutput $OutLog `
    -RedirectStandardError $ErrLog `
    -PassThru

$proc.Id | Set-Content -Encoding ascii -Path $PidFile

$meta = [ordered]@{
    started_at = $startedAt.ToString("s")
    hours = $Hours
    months = $Months
    channels = $Channels
    cycles = $Cycles
    batch_size = $BatchSize
    task_timeout_seconds = $TaskTimeoutSeconds
    pid = $proc.Id
    out_log = $OutLog
    err_log = $ErrLog
}
$meta | ConvertTo-Json | Set-Content -Encoding utf8 -Path $MetaFile

$deadline = $startedAt.AddHours($Hours)
while (-not $proc.HasExited) {
    if ((Get-Date) -ge $deadline) {
        "[$(Get-Date -Format s)] 12h deadline reached; stopping pid $($proc.Id)" |
            Add-Content -Encoding utf8 -Path $ErrLog
        Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        break
    }
    Start-Sleep -Seconds 60
    $proc.Refresh()
}

$finishedAt = Get-Date
$exitCode = if ($proc.HasExited) { $proc.ExitCode } else { $null }
$meta.finished_at = $finishedAt.ToString("s")
$meta.exit_code = $exitCode
$meta.elapsed_minutes = [math]::Round(($finishedAt - $startedAt).TotalMinutes, 1)
$meta | ConvertTo-Json | Set-Content -Encoding utf8 -Path $MetaFile
