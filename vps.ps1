$ErrorActionPreference = "Stop"

$project = "C:\Trading_Reworked"
$baseUrl = "https://raw.githubusercontent.com/theakston472-a11y/Trading_Reworked/vps"
$files = @(
    "requirements-paper-bot.txt",
    "sentry_setup.py",
    "quant/feature_engine.py",
    "quant/institutional_features.py",
    "scripts/alpha_mt5_paper_bot.py",
    "scripts/paper_bot_email.py",
    "scripts/send_paper_bot_email.ps1",
    "scripts/configure_email_alerts.ps1",
    "scripts/watch_alpha_paper_bot.ps1",
    "scripts/setup_paper_bot_watchdog.ps1",
    "scripts/start_alpha_paper_bot.ps1",
    "scripts/check_alpha_paper_bot.ps1",
    "results/session_portfolio_research/best_session_paper_portfolio.csv",
    "results/alpha_mt5_paper/state.json"
)

foreach ($relativePath in $files) {
    $windowsPath = $relativePath.Replace("/", "\")
    $destination = Join-Path $project $windowsPath
    $parent = Split-Path -Parent $destination
    New-Item -ItemType Directory -Path $parent -Force | Out-Null

    if ($relativePath -eq "results/alpha_mt5_paper/state.json" -and
        (Test-Path -LiteralPath $destination)) {
        Write-Host "Preserving existing VPS paper state: $destination"
        continue
    }

    & curl.exe -L --fail "$baseUrl/$relativePath" -o $destination
    if ($LASTEXITCODE -ne 0) {
        throw "Download failed: $relativePath"
    }
    Write-Host "Downloaded: $relativePath"
}

$python = Join-Path $project ".venv\Scripts\python.exe"
if (-not (Test-Path -LiteralPath $python)) {
    throw "Python environment not found at $python"
}

& $python (Join-Path $project "scripts\alpha_mt5_paper_bot.py") --self-test
if ($LASTEXITCODE -ne 0) {
    throw "Paper-bot self-test failed"
}

Write-Host "PAPER BOT FILES READY"
