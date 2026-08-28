$ErrorActionPreference = "Stop"
$watchScript = Join-Path $PSScriptRoot "watch_alpha_paper_bot.ps1"
$taskCommand = "powershell.exe -NoProfile -ExecutionPolicy Bypass -File `"$watchScript`""

& schtasks.exe /Create /TN "Alpha Paper Bot Watchdog" /SC MINUTE /MO 5 /TR $taskCommand /F
if ($LASTEXITCODE -ne 0) {
    throw "Could not create the paper-bot watchdog task."
}

& $watchScript
Write-Host "PAPER BOT WATCHDOG READY"

