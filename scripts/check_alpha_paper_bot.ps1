$ErrorActionPreference = "Stop"
$project = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$python = Join-Path $project ".venv\Scripts\python.exe"
$bot = Join-Path $project "scripts\alpha_mt5_paper_bot.py"
& $python $bot --status --state-dir (Join-Path $project "results\alpha_mt5_paper")
$health = Join-Path $project "results\alpha_mt5_paper\health.json"
if (Test-Path -LiteralPath $health) {
    Write-Host ""
    Write-Host "LATEST HEALTH CHECK"
    Get-Content -LiteralPath $health
}
