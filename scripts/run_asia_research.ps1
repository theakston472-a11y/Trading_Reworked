param()

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Results = Join-Path $Root "results"
$Asia = Join-Path $Results "asia"
$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Archive = Join-Path $Results "asia_runs\$Stamp"

Set-Location $Root

if (-not (Test-Path $Python)) {
    throw "Project Python environment not found: $Python"
}

New-Item -ItemType Directory -Force -Path $Archive | Out-Null

# Archive only Asia-owned outputs. London, New York and funded files are never moved.
if (Test-Path $Asia) {
    Move-Item -LiteralPath $Asia -Destination (Join-Path $Archive "asia")
}

$RootAsiaFiles = Get-ChildItem -LiteralPath $Results -File | Where-Object {
    $_.Name -like "asia_*"
}
if ($RootAsiaFiles) {
    $RootArchive = Join-Path $Archive "root_outputs"
    New-Item -ItemType Directory -Force -Path $RootArchive | Out-Null
    foreach ($File in $RootAsiaFiles) {
        Move-Item -LiteralPath $File.FullName -Destination $RootArchive
    }
}

$Visual = Join-Path $Results "visual_validation_asia"
if (Test-Path $Visual) {
    Move-Item -LiteralPath $Visual -Destination (Join-Path $Archive "visual_validation_asia")
}

New-Item -ItemType Directory -Force -Path (Join-Path $Asia "discovery"), (Join-Path $Asia "logs") | Out-Null

function Start-ResearchProcess {
    param(
        [string[]]$Arguments,
        [string]$Stdout,
        [string]$Stderr
    )
    Start-Process -FilePath $Python -ArgumentList $Arguments -WorkingDirectory $Root `
        -RedirectStandardOutput $Stdout -RedirectStandardError $Stderr `
        -WindowStyle Hidden -PassThru
}

$DiscoveryArguments = @{
    BUY = @(
        ".\scripts\strategy_discovery.py", "--data", ".\quant\feature_database.csv",
        "--db", ".\results\asia\discovery\asia_buy.sqlite",
        "--out", ".\results\asia\discovery\asia_buy.csv",
        "--direction", "BUY", "--session", "Asia", "--max-conditions", "4",
        "--min-trades", "20", "--max-new", "5000", "--rr", "2.0",
        "--max-open", "5", "--max-bars", "48", "--entry-mode", "auto",
        "--entry-wait-bars", "6"
    )
    SELL = @(
        ".\scripts\strategy_discovery.py", "--data", ".\quant\feature_database.csv",
        "--db", ".\results\asia\discovery\asia_sell.sqlite",
        "--out", ".\results\asia\discovery\asia_sell.csv",
        "--direction", "SELL", "--session", "Asia", "--max-conditions", "4",
        "--min-trades", "20", "--max-new", "5000", "--rr", "2.0",
        "--max-open", "5", "--max-bars", "48", "--entry-mode", "auto",
        "--entry-wait-bars", "6"
    )
}

$DiscoveryWall = [Diagnostics.Stopwatch]::StartNew()
$Buy = Start-ResearchProcess -Arguments $DiscoveryArguments.BUY `
    -Stdout (Join-Path $Asia "logs\discovery_buy.log") `
    -Stderr (Join-Path $Asia "logs\discovery_buy.err.log")
$Sell = Start-ResearchProcess -Arguments $DiscoveryArguments.SELL `
    -Stdout (Join-Path $Asia "logs\discovery_sell.log") `
    -Stderr (Join-Path $Asia "logs\discovery_sell.err.log")
$Buy.WaitForExit()
$Sell.WaitForExit()
$DiscoveryWall.Stop()
if ($Buy.ExitCode -ne 0 -or $Sell.ExitCode -ne 0) {
    throw "Asia discovery failed. BUY=$($Buy.ExitCode), SELL=$($Sell.ExitCode). See results\asia\logs."
}

$Promotion = [Diagnostics.Stopwatch]::StartNew()
& $Python ".\scripts\promote_asia_top100.py"
if ($LASTEXITCODE -ne 0) { throw "Asia Top100 promotion failed." }
$Promotion.Stop()

$Rows = Import-Csv ".\results\asia\asia_top100_candidates.csv"
for ($Index = 0; $Index -lt 4; $Index++) {
    $Chunk = @()
    for ($Row = $Index; $Row -lt $Rows.Count; $Row += 4) {
        $Chunk += $Rows[$Row]
    }
    $Worker = $Index + 1
    $Chunk | Export-Csv ".\results\asia\worker_$Worker`_candidates.csv" -NoTypeInformation
}

$DeepArguments = @()
for ($Worker = 1; $Worker -le 4; $Worker++) {
    $DeepArguments += ,@(
        ".\scripts\strategy_lab.py", "--data", ".\quant\feature_database.csv",
        "--candidates", ".\results\asia\worker_$Worker`_candidates.csv",
        "--db", ".\results\asia\worker_$Worker.sqlite",
        "--out", ".\results\asia\worker_$Worker`_strategy_lab.csv",
        "--rr-start", "1.0", "--rr-stop", "7.0", "--rr-step", "0.1",
        "--max-candidates", "25", "--max-bars", "48", "--max-open-trades", "5",
        "--frequency-target", "0.75", "--min-trades", "20", "--final-n", "25",
        "--entry-mode", "auto", "--entry-wait-bars", "6", "--force"
    )
}

$DeepWall = [Diagnostics.Stopwatch]::StartNew()
$Workers = @()
for ($Worker = 1; $Worker -le 4; $Worker++) {
    $Workers += Start-ResearchProcess -Arguments $DeepArguments[$Worker - 1] `
        -Stdout (Join-Path $Asia "logs\strategy_lab_worker_$Worker.log") `
        -Stderr (Join-Path $Asia "logs\strategy_lab_worker_$Worker.err.log")
}
foreach ($Process in $Workers) { $Process.WaitForExit() }
$DeepWall.Stop()
$Failed = @($Workers | Where-Object { $_.ExitCode -ne 0 })
if ($Failed.Count) {
    throw "One or more Asia Strategy Lab workers failed. See results\asia\logs."
}

@(
    [pscustomobject]@{ stage = "discovery_buy_seconds"; seconds = ($Buy.ExitTime - $Buy.StartTime).TotalSeconds },
    [pscustomobject]@{ stage = "discovery_sell_seconds"; seconds = ($Sell.ExitTime - $Sell.StartTime).TotalSeconds },
    [pscustomobject]@{ stage = "parallel_discovery_wall_seconds"; seconds = $DiscoveryWall.Elapsed.TotalSeconds },
    [pscustomobject]@{ stage = "initial_single_deep_seconds"; seconds = 0.0 },
    [pscustomobject]@{ stage = "parallel_deep_phase_seconds"; seconds = $DeepWall.Elapsed.TotalSeconds },
    [pscustomobject]@{ stage = "total_deep_wall_seconds"; seconds = $DeepWall.Elapsed.TotalSeconds },
    [pscustomobject]@{ stage = "promotion_seconds"; seconds = $Promotion.Elapsed.TotalSeconds }
) | Export-Csv (Join-Path $Asia "asia_measured_stage_timings.csv") -NoTypeInformation

& $Python ".\scripts\finalize_asia_research.py"
if ($LASTEXITCODE -ne 0) { throw "Asia finalization failed." }

& $Python ".\scripts\make_visual_validation_asia.py"
if ($LASTEXITCODE -ne 0) { throw "Asia visual validation failed." }

Write-Host "Asia research complete. Previous Asia outputs were archived to: $Archive"
Write-Host "Report: $Results\visual_validation_asia\strategy_report.html"
