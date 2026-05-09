param(
    [ValidateSet("maxsafe", "light", "normal", "full")]
    [string]$Profile = "maxsafe",
    [switch]$SkipLive,
    [switch]$SkipSocial,
    [switch]$SkipArchive,
    [switch]$SkipLinks,
    [switch]$SkipImages,
    [switch]$SkipQualityRepairs,
    [switch]$SkipR2,
    [switch]$SkipUpload,
    [int]$Days = 30,
    [int]$ActiveDays = 7,
    [string]$ArchiveMonths = "",
    [int]$ArchiveCycles = 1
)

$ErrorActionPreference = "Stop"
Set-StrictMode -Version 2.0

$RepoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
Set-Location $RepoRoot

$LogDir = Join-Path $RepoRoot "logs"
$RunDir = Join-Path $RepoRoot "cache\collector_runs"
New-Item -ItemType Directory -Force -Path $LogDir, $RunDir | Out-Null

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$LogPath = Join-Path $LogDir "all_collectors_$Stamp.log"
$LockPath = Join-Path $RunDir "run_all_collectors_latest.lock.json"
$Python = Join-Path $RepoRoot ".venv\Scripts\python.exe"
if (-not (Test-Path $Python)) {
    $Python = "python"
}

function Write-RunLog {
    param([string]$Message)
    $line = "[{0}] {1}" -f (Get-Date -Format "yyyy-MM-dd HH:mm:ss"), $Message
    Write-Host $line
    Add-Content -Path $LogPath -Encoding UTF8 -Value $line
}

function Test-LockIsActive {
    param([string]$Path)
    if (-not (Test-Path $Path)) {
        return $false
    }
    try {
        $lock = Get-Content -Path $Path -Raw -Encoding UTF8 | ConvertFrom-Json
        $proc = Get-CimInstance Win32_Process -Filter ("ProcessId={0}" -f [int]$lock.pid) -ErrorAction SilentlyContinue
        return ($null -ne $proc -and [string]$proc.CommandLine -like "*run_all_collectors_latest.ps1*")
    } catch {
        return $false
    }
}

function Get-ProfileConfig {
    param([string]$Name)
    if ($Name -eq "maxsafe") {
        return @{
            PhaseTimeout = "14400"; FastBrowsers = "2"; DaBrowsers = "1"; R2Workers = "16";
            YoutubePlayer = "50"; YoutubeSurf = "75"; YtAdvertisers = "500"; YtAds = "1500";
            GsAdvertisers = "250"; GsAds = "1000"; ShoppingAds = "250"; MetaPages = "25";
            KakaoMedia = "40"; NaverDaTabs = "6"; MediaProfile = "full";
            Social = @("--discover-limit", "2000", "--content-limit", "500", "--stats-limit", "500", "--news-limit", "300", "--trend-limit", "300", "--per-channel-timeout", "45");
            ArchiveBatch = "5"; ArchiveMaxPrefixes = "5"; ArchiveTimeout = "3600"; LinkLimit = "2000"; ImageLimit = ""; PersonLimit = "300";
        }
    }
    if ($Name -eq "full") {
        return @{
            PhaseTimeout = "14400"; FastBrowsers = "4"; DaBrowsers = "3"; R2Workers = "64";
            YoutubePlayer = "50"; YoutubeSurf = "75"; YtAdvertisers = "500"; YtAds = "1500";
            GsAdvertisers = "250"; GsAds = "1000"; ShoppingAds = "250"; MetaPages = "25";
            KakaoMedia = "40"; NaverDaTabs = "6"; MediaProfile = "full";
            Social = @("--discover-limit", "2000", "--content-limit", "500", "--stats-limit", "500", "--news-limit", "300", "--trend-limit", "300", "--per-channel-timeout", "45");
            ArchiveBatch = "5"; ArchiveMaxPrefixes = "5"; ArchiveTimeout = "3600"; LinkLimit = "2000"; ImageLimit = ""; PersonLimit = "300";
        }
    }
    if ($Name -eq "normal") {
        return @{
            PhaseTimeout = "10800"; FastBrowsers = "3"; DaBrowsers = "2"; R2Workers = "24";
            YoutubePlayer = "25"; YoutubeSurf = "40"; YtAdvertisers = "300"; YtAds = "900";
            GsAdvertisers = "150"; GsAds = "600"; ShoppingAds = "160"; MetaPages = "12";
            KakaoMedia = "20"; NaverDaTabs = "4"; MediaProfile = "balanced";
            Social = @("--discover-limit", "1200", "--content-limit", "300", "--stats-limit", "300", "--news-limit", "150", "--trend-limit", "200", "--per-channel-timeout", "35");
            ArchiveBatch = "5"; ArchiveMaxPrefixes = "3"; ArchiveTimeout = "1800"; LinkLimit = "1200"; ImageLimit = "2000"; PersonLimit = "200";
        }
    }
    return @{
        PhaseTimeout = "7200"; FastBrowsers = "2"; DaBrowsers = "1"; R2Workers = "12";
        YoutubePlayer = "12"; YoutubeSurf = "18"; YtAdvertisers = "120"; YtAds = "360";
        GsAdvertisers = "80"; GsAds = "300"; ShoppingAds = "80"; MetaPages = "6";
        KakaoMedia = "10"; NaverDaTabs = "3"; MediaProfile = "balanced";
        Social = @("--discover-limit", "600", "--content-limit", "150", "--stats-limit", "150", "--news-limit", "80", "--trend-limit", "120", "--per-channel-timeout", "25");
        ArchiveBatch = "3"; ArchiveMaxPrefixes = "2"; ArchiveTimeout = "900"; LinkLimit = "600"; ImageLimit = "1000"; PersonLimit = "100";
    }
}

function Invoke-PythonStep {
    param(
        [string]$Name,
        [string[]]$Arguments,
        [hashtable]$Env = @{},
        [switch]$AllowFail
    )

    Write-RunLog ("START {0}: {1} {2}" -f $Name, $Python, ($Arguments -join " "))
    $backup = @{}
    foreach ($key in $Env.Keys) {
        $backup[$key] = [Environment]::GetEnvironmentVariable($key, "Process")
        [Environment]::SetEnvironmentVariable($key, [string]$Env[$key], "Process")
    }
    $backup["PYTHONIOENCODING"] = [Environment]::GetEnvironmentVariable("PYTHONIOENCODING", "Process")
    [Environment]::SetEnvironmentVariable("PYTHONIOENCODING", "utf-8", "Process")

    $started = Get-Date
    try {
        & $Python @Arguments 2>&1 | ForEach-Object {
            $text = [string]$_
            Write-Host $text
            Add-Content -Path $LogPath -Encoding UTF8 -Value $text
        }
        $code = $LASTEXITCODE
        $elapsed = [int]((Get-Date) - $started).TotalSeconds
        Write-RunLog ("END {0}: exit={1} elapsed={2}s" -f $Name, $code, $elapsed)
        if ($code -ne 0 -and -not $AllowFail) {
            throw "$Name failed with exit code $code"
        }
    } finally {
        foreach ($key in $backup.Keys) {
            [Environment]::SetEnvironmentVariable($key, $backup[$key], "Process")
        }
    }
}

if (Test-LockIsActive $LockPath) {
    throw "Another all-collector run is already active. Stop it before starting a new one."
}
@{ pid = $PID; started_at = (Get-Date).ToString("s"); profile = $Profile } |
    ConvertTo-Json -Compress |
    Set-Content -Path $LockPath -Encoding UTF8

try {
    $cfg = Get-ProfileConfig $Profile
    if ([string]::IsNullOrWhiteSpace($ArchiveMonths)) {
        $ArchiveMonths = Get-Date -Format "yyyy-MM"
    }

    $commonEnv = @{
        "COMBINED_CRAWL_PHASE_TIMEOUT" = $cfg.PhaseTimeout;
        "COMBINED_CRAWL_UPLOAD_R2_AFTER_PHASE" = "1";
        "COMBINED_CRAWL_LOG" = (Join-Path $LogDir "combined_crawl_$Stamp.log");
        "FAST_CRAWL_MAX_BROWSERS" = $cfg.FastBrowsers;
        "DA_CRAWL_MAX_BROWSERS" = $cfg.DaBrowsers;
        "R2_UPLOAD_WORKERS" = $cfg.R2Workers;
        "R2_UPLOAD_TIMEOUT" = "7200";
        "YOUTUBE_PLAYER_SAMPLES" = $cfg.YoutubePlayer;
        "YOUTUBE_SURF_SAMPLES" = $cfg.YoutubeSurf;
        "YT_ADS_MAX_ADVERTISERS" = $cfg.YtAdvertisers;
        "YT_ADS_MAX_ADS" = $cfg.YtAds;
        "GS_ADS_MAX_ADVERTISERS" = $cfg.GsAdvertisers;
        "GS_ADS_MAX_ADS" = $cfg.GsAds;
        "NAVER_SHOP_MAX_ADS" = $cfg.ShoppingAds;
        "META_MAX_PAGES" = $cfg.MetaPages;
        "KAKAO_MAX_MEDIA" = $cfg.KakaoMedia;
        "NAVER_DA_CATEGORY_TABS" = $cfg.NaverDaTabs;
        "MEDIA_COLLECTION_PROFILE" = $cfg.MediaProfile;
        "CRAWLER_WARMUP_SITE_COUNT" = "0";
    }

    Write-RunLog ("AdScope collector run profile={0} months={1} log={2}" -f $Profile, $ArchiveMonths, $LogPath)
    Write-RunLog "Live ad collection is set to 8 hours: two 4-hour phases."
    Write-RunLog "Stages are sequential to avoid browser storms and SQLite lock pressure."

    if (-not $SkipLive) {
        Invoke-PythonStep -Name "live-ad-collectors" -Arguments @("scripts/run_combined_crawl.py") -Env $commonEnv
    }
    if (-not $SkipSocial) {
        Invoke-PythonStep -Name "social-meta-signal" -Arguments (@("scripts/run_social_signal_boost.py") + $cfg.Social) -Env $commonEnv
    }
    if (-not $SkipArchive) {
        Invoke-PythonStep -Name "archive-round-robin" -Arguments @(
            "scripts/run_archive_round_robin.py",
            "--months", $ArchiveMonths,
            "--channels", "gdn,yt,search,meta,tiktok",
            "--cycles", [string]$ArchiveCycles,
            "--batch-size", $cfg.ArchiveBatch,
            "--max-prefixes", $cfg.ArchiveMaxPrefixes,
            "--timeout", $cfg.ArchiveTimeout,
            "--include-all-prefixes",
            "--queue-strategy", "coverage",
            "--skip-completed"
        ) -Env $commonEnv
    }
    if (-not $SkipLinks) {
        Invoke-PythonStep -Name "advertiser-url-and-social-link-backfill" -Arguments @(
            "scripts/backfill_advertiser_links.py",
            "--limit", $cfg.LinkLimit
        ) -Env $commonEnv
    }
    if (-not $SkipImages) {
        $imageArgs = @(
            "scripts/backfill_ad_images.py",
            "--days", [string]$Days,
            "--reject-unrecoverable"
        )
        if (-not [string]::IsNullOrWhiteSpace($cfg.ImageLimit)) {
            $imageArgs += @("--limit", $cfg.ImageLimit)
        }
        Invoke-PythonStep -Name "creative-asset-backfill" -Arguments $imageArgs -Env $commonEnv
    }
    if (-not $SkipQualityRepairs) {
        Invoke-PythonStep -Name "person-name-advertiser-repair" -Arguments @(
            "scripts/fix_person_name_advertisers.py",
            "--limit", $cfg.PersonLimit
        ) -Env $commonEnv -AllowFail
        Invoke-PythonStep -Name "merge-advertisers-by-website" -Arguments @(
            "scripts/merge_advertisers_by_website.py"
        ) -Env $commonEnv
        Invoke-PythonStep -Name "advertiser-campaign-integrity-repair" -Arguments @(
            "scripts/repair_advertiser_campaign_integrity.py"
        ) -Env $commonEnv
        Invoke-PythonStep -Name "recent-quality-repair" -Arguments @(
            "scripts/repair_recent_quality_gate.py",
            "--days", [string]$Days
        ) -Env $commonEnv
        Invoke-PythonStep -Name "known-advertiser-taxonomy-repair" -Arguments @(
            "scripts/repair_known_advertiser_taxonomy.py"
        ) -Env $commonEnv
        Invoke-PythonStep -Name "invalid-label-and-copy-quality-repair" -Arguments @(
            "scripts/reject_invalid_labels.py",
            "--days", [string]$Days,
            "--apply",
            "--repair-campaign-names"
        ) -Env $commonEnv
    }
    if (-not $SkipR2) {
        Invoke-PythonStep -Name "r2-image-upload" -Arguments @("scripts/upload_images_to_r2.py") -Env $commonEnv
    }
    if (-not $SkipUpload) {
        Invoke-PythonStep -Name "quality-rebuild-and-db-upload" -Arguments @(
            "scripts/filter_and_deploy_current.py",
            "--days", [string]$Days,
            "--active-days", [string]$ActiveDays,
            "--keep-snapshot"
        ) -Env $commonEnv
    }

    Write-RunLog "ALL DONE"
} finally {
    Remove-Item -Path $LockPath -Force -ErrorAction SilentlyContinue
}
