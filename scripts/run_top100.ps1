param(
    [int]$MaxOpenTrades=5,
    [int]$MinTrades=20,
    [double]$FrequencyTarget=0.75,
    [ValidateSet("auto","next_open","signal_close","fib_touch")]
    [string]$EntryMode="auto",
    [int]$EntryWaitBars=6,
    [switch]$Charts,
    [switch]$Force
)

$Root = Split-Path -Parent $PSScriptRoot
$c = Join-Path $Root "quant\top100_candidates.csv"

if (-not (Test-Path $c)) {
    Write-Error "Top-100 file not found. Run promote_family_top100.py first."
    exit 1
}

$args = @(
    (Join-Path $PSScriptRoot "strategy_lab.py"),
    "--candidates", $c,
    "--max-candidates", "100",

    # BIG SEARCH already tested 0.1 RR steps.
    # Top 100 uses 0.5 steps for deeper validation.
    "--rr-start", "1.0",
    "--rr-stop", "7.0",
    "--rr-step", "0.5",

    "--max-open-trades", $MaxOpenTrades,
    "--min-trades", $MinTrades,
    "--frequency-target", $FrequencyTarget,
    "--entry-mode", $EntryMode,
    "--entry-wait-bars", $EntryWaitBars,
    "--final-n", "20"
)

if ($Charts) {
    $args += "--charts"
}

if ($Force) {
    $args += "--force"
}

python @args

if ($LASTEXITCODE -ne 0) {
    exit $LASTEXITCODE
}