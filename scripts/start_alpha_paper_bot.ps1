$ErrorActionPreference = "Stop"
$project = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$python = Join-Path $project ".venv\Scripts\python.exe"
$bot = Join-Path $project "scripts\alpha_mt5_paper_bot.py"
$shortlist = Join-Path $project "results\session_portfolio_research\best_session_paper_portfolio.csv"
$stateDirectory = Join-Path $project "results\alpha_mt5_paper"

if (-not (Test-Path -LiteralPath $python)) {
    throw "The permanent paper-bot environment is missing. Run scripts\setup_alpha_paper_bot.ps1 first."
}

$existing = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*alpha_mt5_paper_bot.py*" -and $_.Name -like "python*" }
if ($existing) {
    Write-Host "Paper bot is already running. PID: $($existing.ProcessId)"
    exit 0
}

$state = Get-Content -LiteralPath (Join-Path $stateDirectory "state.json") -Raw | ConvertFrom-Json
if ($state.positions.Count -ne 0 -or $state.pending.Count -ne 0) {
    Write-Host "Resuming saved open/pending paper state; no broker order will be sent."
}

$stdout = Join-Path $stateDirectory "bot_runtime_stdout.log"
$stderr = Join-Path $stateDirectory "bot_runtime_stderr.log"
$arguments = @("-u", $bot, "--shortlist", $shortlist, "--interval", "60")
$process = Start-Process -FilePath $python -ArgumentList $arguments -WorkingDirectory $project `
    -WindowStyle Hidden -RedirectStandardOutput $stdout -RedirectStandardError $stderr -PassThru
Write-Host "Paper-only bot started in the background. PID: $($process.Id)"
Write-Host "Status command: & '$python' '$bot' --status"
