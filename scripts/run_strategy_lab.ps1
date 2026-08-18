param(
    [string]$Data = "",
    [string]$Candidates = "",
    [string]$Start = "2025-01-01",
    [string]$End = "",
    [int]$MaxCandidates = 100,
    [switch]$AllCandidates,
    [int]$MaxOpenTrades = 5,
    [double]$FrequencyTarget = 0.75,
    [int]$MinTrades = 20,
    [ValidateSet("auto","next_open","signal_close","fib_touch")]
    [string]$EntryMode = "auto",
    [int]$EntryWaitBars = 6,
    [switch]$Charts,
    [switch]$Force
)

$Root = Split-Path -Parent $PSScriptRoot
$Script = Join-Path $PSScriptRoot "strategy_lab.py"

$args = @(
    $Script,
    "--start", $Start,
    "--rr-start", "1.0",
    "--rr-stop", "7.0",
    "--rr-step", "0.5",
    "--max-candidates", $MaxCandidates,
    "--max-open-trades", $MaxOpenTrades,
    "--frequency-target", $FrequencyTarget,
    "--min-trades", $MinTrades,
    "--entry-mode", $EntryMode,
    "--entry-wait-bars", $EntryWaitBars
)

if ($Data -ne "") { $args += @("--data", $Data) }
if ($Candidates -ne "") { $args += @("--candidates", $Candidates) }
if ($End -ne "") { $args += @("--end", $End) }
if ($AllCandidates) { $args += "--all-candidates" }
if ($Charts) { $args += "--charts" }
if ($Force) { $args += "--force" }

Write-Host ""
Write-Host "Trading Strategy Lab" -ForegroundColor Cyan
Write-Host "RR: 1.0 -> 7.0 in 0.5 increments"
Write-Host "Entry model: $EntryMode (Fib wait bars: $EntryWaitBars)"
Write-Host "Overlapping trades: allowed, maximum open = $MaxOpenTrades"
Write-Host "Cache: already-tested strategy/RR/period combinations are skipped"
Write-Host ""

python @args
if ($LASTEXITCODE -ne 0) {
    Write-Error "Strategy lab failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}
