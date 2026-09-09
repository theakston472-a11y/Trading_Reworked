param(
    [int]$HealthTimeoutMinutes = 10
)

$ErrorActionPreference = "Stop"
$project = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stateDirectory = Join-Path $project "results\alpha_mt5_paper"
$healthPath = Join-Path $stateDirectory "health.json"
$watchStatePath = Join-Path $stateDirectory "watchdog_state.json"
$senderScript = Join-Path $PSScriptRoot "send_paper_bot_email.ps1"
$startScript = Join-Path $PSScriptRoot "start_alpha_paper_bot.ps1"

New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null

function Send-WatchdogEmail([string]$subject, [string]$body) {
    try {
        & $senderScript -Subject $subject -Body $body
    }
    catch {
        Write-Warning "Watchdog email failed: $($_.Exception.Message)"
    }
}

$previous = @{ alert_active = $false }
if (Test-Path -LiteralPath $watchStatePath) {
    try {
        $previous = Get-Content -LiteralPath $watchStatePath -Raw | ConvertFrom-Json
    }
    catch {
        Write-Warning "Previous watchdog state could not be read; starting a fresh check."
    }
}

function Get-PaperBotProcesses {
    return @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*alpha_mt5_paper_bot.py*" -and $_.Name -like "python*" })
}

$processes = @(Get-PaperBotProcesses)
$running = $processes.Count -gt 0
$healthFresh = $false
$healthAgeMinutes = $null
$reason = "Paper bot process is not running."

if ($running -and (Test-Path -LiteralPath $healthPath)) {
    try {
        $health = Get-Content -LiteralPath $healthPath -Raw | ConvertFrom-Json
        $checkedAt = [DateTimeOffset]::Parse([string]$health.checked_at)
        $healthAgeMinutes = ((Get-Date).ToUniversalTime() - $checkedAt.UtcDateTime).TotalMinutes
        $healthFresh = $healthAgeMinutes -le $HealthTimeoutMinutes
        if (-not $healthFresh) {
            $reason = "Paper bot health file is $([math]::Round($healthAgeMinutes, 1)) minutes old."
        }
    }
    catch {
        $reason = "Paper bot health file could not be read."
    }
}
elseif ($running) {
    $reason = "Paper bot is running but has not created a health file."
}

$healthy = $running -and $healthFresh
$restartRequested = $false
$restartResult = "NONE"
if (-not $healthy -and -not [bool]$previous.alert_active) {
    Send-WatchdogEmail "Paper Bot - WARNING" @"
The independent VPS watchdog detected a problem.

$reason
Time UTC: $([DateTime]::UtcNow.ToString("o"))
The watchdog will attempt to restart the paper-only bot.
"@
}

if (-not $healthy) {
    try {
        if ($running) {
            foreach ($process in $processes) {
                Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
            }
            Start-Sleep -Seconds 2
            Write-Host "Watchdog stopped the stale paper-bot process."
        }
        & $startScript
        $restartRequested = $true
        $restartResult = "REQUESTED"
        Write-Host "Watchdog requested a paper-bot restart."
    }
    catch {
        $restartResult = "FAILED: $($_.Exception.Message)"
        Write-Warning "Automatic restart failed: $($_.Exception.Message)"
    }
}

if ($healthy -and [bool]$previous.alert_active) {
    Send-WatchdogEmail "Paper Bot - RECOVERED" @"
The paper bot is running and its health updates are current again.

Time UTC: $([DateTime]::UtcNow.ToString("o"))
"@
}

[ordered]@{
    checked_at = [DateTime]::UtcNow.ToString("o")
    alert_active = (-not $healthy)
    process_running = $running
    health_fresh = $healthFresh
    health_age_minutes = $healthAgeMinutes
    reason = if ($healthy) { "OK" } else { $reason }
    restart_requested = $restartRequested
    restart_result = $restartResult
} | ConvertTo-Json | Set-Content -LiteralPath $watchStatePath -Encoding UTF8
