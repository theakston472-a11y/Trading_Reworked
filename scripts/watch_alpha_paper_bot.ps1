$ErrorActionPreference = "Stop"
$project = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stateDirectory = Join-Path $project "results\alpha_mt5_paper"
$healthPath = Join-Path $stateDirectory "health.json"
$watchStatePath = Join-Path $stateDirectory "watchdog_state.json"
$senderScript = Join-Path $PSScriptRoot "send_paper_bot_email.ps1"
$startScript = Join-Path $PSScriptRoot "start_alpha_paper_bot.ps1"

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
    $previous = Get-Content -LiteralPath $watchStatePath -Raw | ConvertFrom-Json
}

$processes = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*alpha_mt5_paper_bot.py*" -and $_.Name -like "python*" })
$running = $processes.Count -gt 0
$healthFresh = $false
$healthAgeMinutes = $null
$reason = "Paper bot process is not running."

if ($running -and (Test-Path -LiteralPath $healthPath)) {
    try {
        $health = Get-Content -LiteralPath $healthPath -Raw | ConvertFrom-Json
        $checkedAt = [DateTimeOffset]::Parse([string]$health.checked_at)
        $healthAgeMinutes = ((Get-Date).ToUniversalTime() - $checkedAt.UtcDateTime).TotalMinutes
        $healthFresh = $healthAgeMinutes -le 10
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
if (-not $healthy -and -not [bool]$previous.alert_active) {
    Send-WatchdogEmail "Paper Bot - WARNING" @"
The independent VPS watchdog detected a problem.

$reason
Time UTC: $([DateTime]::UtcNow.ToString("o"))
The watchdog will attempt to restart the bot if its process is missing.
"@
}

if (-not $running) {
    try {
        & $startScript
        Write-Host "Watchdog requested a paper-bot restart."
    }
    catch {
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
} | ConvertTo-Json | Set-Content -LiteralPath $watchStatePath -Encoding UTF8

