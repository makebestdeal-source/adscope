#Requires -Version 5.1
<#
.SYNOPSIS
    AdScope Scheduler - NSSM Windows Service Manager (PowerShell)

.DESCRIPTION
    Installs, removes, starts, stops, or checks the AdScopeScheduler Windows
    service using NSSM (Non-Sucking Service Manager). Downloads NSSM
    automatically if not found.

.PARAMETER Action
    install  - Install and optionally start the service (default)
    remove   - Stop and remove the service
    start    - Start the service
    stop     - Stop the service
    restart  - Restart the service
    status   - Show service status

.EXAMPLE
    .\install_scheduler_service.ps1
    .\install_scheduler_service.ps1 -Action install
    .\install_scheduler_service.ps1 -Action status
    .\install_scheduler_service.ps1 -Action stop
    .\install_scheduler_service.ps1 -Action remove

.NOTES
    Must be run as Administrator for install/remove/start/stop.
#>

[CmdletBinding()]
param(
    [ValidateSet('install', 'remove', 'start', 'stop', 'restart', 'status')]
    [string]$Action = 'install'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ---------------------------------------------------------------
# Constants
# ---------------------------------------------------------------
$ServiceName  = 'AdScopeScheduler'
$Description  = 'AdScope Scheduler - Automated ad crawling service'
$NssmUrl      = 'https://nssm.cc/release/nssm-2.24.zip'
$NssmZipPath  = "$env:TEMP\nssm.zip"
$NssmExtract  = "$env:TEMP\nssm_extract"
$NssmInstall  = 'C:\nssm'

# Project root = parent of scripts\
$ScriptDir  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = (Resolve-Path (Join-Path $ScriptDir '..')).Path
$LogDir     = Join-Path $ProjectDir 'logs'
$StdoutLog  = Join-Path $LogDir 'scheduler_service.log'
$StderrLog  = Join-Path $LogDir 'scheduler_service_err.log'

# ---------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------
function Write-Header {
    param([string]$Text)
    $line = '=' * 62
    Write-Host ""
    Write-Host $line -ForegroundColor Cyan
    Write-Host "  $Text" -ForegroundColor Cyan
    Write-Host $line -ForegroundColor Cyan
}

function Write-Step {
    param([string]$Step, [string]$Text)
    Write-Host "  [$Step] $Text" -ForegroundColor Yellow
}

function Write-OK {
    param([string]$Text)
    Write-Host "  [OK] $Text" -ForegroundColor Green
}

function Write-Fail {
    param([string]$Text)
    Write-Host "  [FAIL] $Text" -ForegroundColor Red
}

function Write-Info {
    param([string]$Text)
    Write-Host "  [INFO] $Text" -ForegroundColor Gray
}

function Assert-Admin {
    $principal = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
        Write-Fail "This script must be run as Administrator."
        Write-Host ""
        Write-Host "  Right-click PowerShell -> 'Run as Administrator', then re-run:" -ForegroundColor Yellow
        Write-Host "    .\install_scheduler_service.ps1 -Action $Action" -ForegroundColor White
        exit 1
    }
}

# ---------------------------------------------------------------
# Locate or download nssm.exe
# ---------------------------------------------------------------
function Get-NssmPath {
    # 1. Common fixed locations
    $candidates = @(
        'C:\nssm\nssm.exe',
        'C:\nssm\win64\nssm.exe',
        'C:\tools\nssm\nssm.exe',
        'C:\ProgramData\chocolatey\bin\nssm.exe'
    )
    foreach ($c in $candidates) {
        if (Test-Path $c) { return $c }
    }

    # 2. In PATH
    $inPath = Get-Command nssm -ErrorAction SilentlyContinue
    if ($inPath) { return $inPath.Source }

    return $null
}

function Install-Nssm {
    Write-Header "Downloading NSSM"
    Write-Info "nssm.exe not found. Attempting automatic download..."
    Write-Info "Source: $NssmUrl"

    try {
        [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
        Write-Step "1/3" "Downloading nssm-2.24.zip..."
        Invoke-WebRequest -Uri $NssmUrl -OutFile $NssmZipPath -UseBasicParsing
        Write-OK "Download complete."

        Write-Step "2/3" "Extracting archive..."
        if (Test-Path $NssmExtract) { Remove-Item $NssmExtract -Recurse -Force }
        Expand-Archive -Path $NssmZipPath -DestinationPath $NssmExtract
        Write-OK "Extraction complete."

        Write-Step "3/3" "Installing to $NssmInstall..."
        if (-not (Test-Path $NssmInstall)) { New-Item -ItemType Directory -Path $NssmInstall | Out-Null }

        # Prefer 64-bit binary
        $nssmBin = Get-ChildItem "$NssmExtract\*\win64\nssm.exe" -ErrorAction SilentlyContinue |
                   Select-Object -First 1
        if (-not $nssmBin) {
            $nssmBin = Get-ChildItem "$NssmExtract\*\win32\nssm.exe" -ErrorAction SilentlyContinue |
                       Select-Object -First 1
        }
        if (-not $nssmBin) {
            $nssmBin = Get-ChildItem "$NssmExtract\nssm.exe" -ErrorAction SilentlyContinue |
                       Select-Object -First 1
        }

        if (-not $nssmBin) {
            throw "Could not locate nssm.exe inside the downloaded archive."
        }

        Copy-Item $nssmBin.FullName "$NssmInstall\nssm.exe" -Force
        Write-OK "nssm.exe installed to $NssmInstall\nssm.exe"

        # Cleanup temp files
        Remove-Item $NssmZipPath  -Force -ErrorAction SilentlyContinue
        Remove-Item $NssmExtract  -Recurse -Force -ErrorAction SilentlyContinue

        return "$NssmInstall\nssm.exe"
    }
    catch {
        Write-Fail "Automatic download failed: $_"
        Write-Host ""
        Write-Host "  Manual installation options:" -ForegroundColor Yellow
        Write-Host "    1. Chocolatey (run as Admin):"
        Write-Host "         choco install nssm"
        Write-Host ""
        Write-Host "    2. Download manually:"
        Write-Host "         $NssmUrl"
        Write-Host "         Extract nssm.exe -> C:\nssm\"
        Write-Host ""
        exit 1
    }
}

# ---------------------------------------------------------------
# Locate python.exe
# ---------------------------------------------------------------
function Get-PythonExe {
    $py = Get-Command python -ErrorAction SilentlyContinue
    if ($py) { return $py.Source }

    # Check common venv locations relative to project
    $venvCandidates = @(
        (Join-Path $ProjectDir '.venv\Scripts\python.exe'),
        (Join-Path $ProjectDir 'venv\Scripts\python.exe'),
        (Join-Path $ProjectDir 'env\Scripts\python.exe')
    )
    foreach ($c in $venvCandidates) {
        if (Test-Path $c) { return $c }
    }

    return $null
}

# ---------------------------------------------------------------
# Service status helper
# ---------------------------------------------------------------
function Get-ServiceStatus {
    param([string]$Name)
    $svc = Get-Service -Name $Name -ErrorAction SilentlyContinue
    if (-not $svc) { return 'NotInstalled' }
    return $svc.Status.ToString()
}

function Show-Status {
    param([string]$Nssm)
    Write-Header "Service Status: $ServiceName"

    $status = Get-ServiceStatus -Name $ServiceName
    if ($status -eq 'NotInstalled') {
        Write-Info "Service is NOT installed."
        return
    }

    $color = switch ($status) {
        'Running' { 'Green' }
        'Stopped' { 'Yellow' }
        default   { 'Red' }
    }
    Write-Host "  Status      : " -NoNewline
    Write-Host $status -ForegroundColor $color

    $svc = Get-WmiObject Win32_Service -Filter "Name='$ServiceName'" -ErrorAction SilentlyContinue
    if ($svc) {
        Write-Host "  Start Type  : $($svc.StartMode)"
        Write-Host "  Binary Path : $($svc.PathName)"
        Write-Host "  Description : $($svc.Description)"
    }

    Write-Host "  Stdout log  : $StdoutLog"
    Write-Host "  Stderr log  : $StderrLog"
    Write-Host "  App log dir : $LogDir\scheduler_YYYY-MM-DD.log"
    Write-Host ""
}

# ---------------------------------------------------------------
# INSTALL
# ---------------------------------------------------------------
function Install-Service {
    param([string]$Nssm, [string]$PythonExe)

    Write-Header "Installing $ServiceName"

    Write-Info "Project dir : $ProjectDir"
    Write-Info "Python      : $PythonExe"
    Write-Info "nssm        : $Nssm"
    Write-Info "Stdout log  : $StdoutLog"
    Write-Info "Stderr log  : $StderrLog"

    # Create log directory
    if (-not (Test-Path $LogDir)) {
        New-Item -ItemType Directory -Path $LogDir | Out-Null
        Write-OK "Created log directory: $LogDir"
    }

    # Remove existing service if present
    $existingStatus = Get-ServiceStatus -Name $ServiceName
    if ($existingStatus -ne 'NotInstalled') {
        Write-Info "Existing service found (status: $existingStatus). Removing..."
        if ($existingStatus -eq 'Running') {
            & $Nssm stop $ServiceName | Out-Null
            Start-Sleep -Seconds 3
        }
        & $Nssm remove $ServiceName confirm | Out-Null
        Start-Sleep -Seconds 2
        Write-OK "Existing service removed."
    }

    Write-Step " 1/9" "Installing service..."
    & $Nssm install $ServiceName $PythonExe "scripts\run_scheduler.py"
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "nssm install failed (exit code $LASTEXITCODE)."
        exit 1
    }

    Write-Step " 2/9" "AppDirectory -> $ProjectDir"
    & $Nssm set $ServiceName AppDirectory $ProjectDir

    Write-Step " 3/9" "AppParameters -> scripts\run_scheduler.py"
    & $Nssm set $ServiceName AppParameters "scripts\run_scheduler.py"

    Write-Step " 4/9" "AppStdout -> $StdoutLog"
    & $Nssm set $ServiceName AppStdout $StdoutLog

    Write-Step " 5/9" "AppStderr -> $StderrLog"
    & $Nssm set $ServiceName AppStderr $StderrLog

    Write-Step " 6/9" "AppRotateFiles = 1, AppRotateBytes = 10485760 (10 MB)"
    & $Nssm set $ServiceName AppRotateFiles 1
    & $Nssm set $ServiceName AppRotateBytes 10485760

    Write-Step " 7/9" "Start type -> SERVICE_AUTO_START"
    & $Nssm set $ServiceName Start SERVICE_AUTO_START

    Write-Step " 8/9" "Description -> $Description"
    & $Nssm set $ServiceName Description $Description

    Write-Step " 9/9" "AppRestartDelay -> 10000 ms"
    & $Nssm set $ServiceName AppRestartDelay 10000

    Write-OK "Service '$ServiceName' installed successfully."
    Write-Host ""
    Write-Host "  Quick commands:" -ForegroundColor Cyan
    Write-Host "    Start   :  .\install_scheduler_service.ps1 -Action start"
    Write-Host "    Stop    :  .\install_scheduler_service.ps1 -Action stop"
    Write-Host "    Restart :  .\install_scheduler_service.ps1 -Action restart"
    Write-Host "    Status  :  .\install_scheduler_service.ps1 -Action status"
    Write-Host "    Remove  :  .\install_scheduler_service.ps1 -Action remove"
    Write-Host ""
    Write-Host "  Or using sc / nssm directly:"
    Write-Host "    nssm start   $ServiceName"
    Write-Host "    nssm stop    $ServiceName"
    Write-Host "    nssm status  $ServiceName"
    Write-Host "    nssm edit    $ServiceName"
    Write-Host ""

    $answer = Read-Host "  Start the service now? (Y/N)"
    if ($answer -match '^[Yy]') {
        Start-ServiceAction -Nssm $Nssm
    }
}

# ---------------------------------------------------------------
# REMOVE
# ---------------------------------------------------------------
function Remove-Service {
    param([string]$Nssm)

    Write-Header "Removing $ServiceName"

    $status = Get-ServiceStatus -Name $ServiceName
    if ($status -eq 'NotInstalled') {
        Write-Info "Service '$ServiceName' is not installed. Nothing to do."
        return
    }

    if ($status -eq 'Running') {
        Write-Step "1/3" "Stopping service (status: $status)..."
        & $Nssm stop $ServiceName
        Start-Sleep -Seconds 5
    }

    Write-Step "2/3" "Removing service..."
    & $Nssm remove $ServiceName confirm
    if ($LASTEXITCODE -ne 0) {
        Write-Fail "nssm remove failed (exit code $LASTEXITCODE)."
        exit 1
    }

    Write-Step "3/3" "Done."
    Write-OK "Service '$ServiceName' removed."
    Write-Info "Log files are preserved at: $LogDir"
    Write-Host ""
}

# ---------------------------------------------------------------
# START / STOP / RESTART
# ---------------------------------------------------------------
function Start-ServiceAction {
    param([string]$Nssm)
    Write-Header "Starting $ServiceName"
    $status = Get-ServiceStatus -Name $ServiceName
    if ($status -eq 'NotInstalled') {
        Write-Fail "Service is not installed. Run: .\install_scheduler_service.ps1 -Action install"
        exit 1
    }
    if ($status -eq 'Running') {
        Write-Info "Service is already running."
        Show-Status -Nssm $Nssm
        return
    }
    & $Nssm start $ServiceName
    Start-Sleep -Seconds 3
    $newStatus = Get-ServiceStatus -Name $ServiceName
    if ($newStatus -eq 'Running') {
        Write-OK "Service started successfully."
    } else {
        Write-Fail "Service status after start: $newStatus"
        Write-Info "Check logs: $StderrLog"
    }
    Show-Status -Nssm $Nssm
}

function Stop-ServiceAction {
    param([string]$Nssm)
    Write-Header "Stopping $ServiceName"
    $status = Get-ServiceStatus -Name $ServiceName
    if ($status -eq 'NotInstalled') {
        Write-Fail "Service is not installed."
        exit 1
    }
    if ($status -eq 'Stopped') {
        Write-Info "Service is already stopped."
        return
    }
    & $Nssm stop $ServiceName
    Start-Sleep -Seconds 3
    $newStatus = Get-ServiceStatus -Name $ServiceName
    if ($newStatus -eq 'Stopped') {
        Write-OK "Service stopped."
    } else {
        Write-Fail "Service status after stop: $newStatus"
    }
}

function Restart-ServiceAction {
    param([string]$Nssm)
    Write-Header "Restarting $ServiceName"
    $status = Get-ServiceStatus -Name $ServiceName
    if ($status -eq 'NotInstalled') {
        Write-Fail "Service is not installed."
        exit 1
    }
    & $Nssm restart $ServiceName
    Start-Sleep -Seconds 4
    $newStatus = Get-ServiceStatus -Name $ServiceName
    if ($newStatus -eq 'Running') {
        Write-OK "Service restarted successfully."
    } else {
        Write-Fail "Service status after restart: $newStatus"
        Write-Info "Check logs: $StderrLog"
    }
    Show-Status -Nssm $Nssm
}

# ---------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------
Write-Host ""
Write-Host "  AdScope Scheduler Service Manager" -ForegroundColor Cyan
Write-Host "  Action: $Action" -ForegroundColor Cyan

# Admin check for mutating actions
if ($Action -in @('install', 'remove', 'start', 'stop', 'restart')) {
    Assert-Admin
}

# Locate nssm (status only needs it for nssm-based queries; still useful)
$nssm = Get-NssmPath
if (-not $nssm) {
    if ($Action -eq 'install') {
        $nssm = Install-Nssm
    } elseif ($Action -eq 'status') {
        # status can work with Get-Service alone
        $nssm = 'nssm'  # placeholder; won't be called for pure status
    } else {
        Write-Fail "nssm.exe not found. Run install first or install nssm manually."
        exit 1
    }
}

switch ($Action) {
    'install' {
        $pythonExe = Get-PythonExe
        if (-not $pythonExe) {
            Write-Fail "python.exe not found. Activate your virtual environment or add Python to PATH."
            exit 1
        }
        Install-Service -Nssm $nssm -PythonExe $pythonExe
    }
    'remove'  { Remove-Service  -Nssm $nssm }
    'start'   { Start-ServiceAction   -Nssm $nssm }
    'stop'    { Stop-ServiceAction    -Nssm $nssm }
    'restart' { Restart-ServiceAction -Nssm $nssm }
    'status'  { Show-Status     -Nssm $nssm }
}

Write-Host ""
