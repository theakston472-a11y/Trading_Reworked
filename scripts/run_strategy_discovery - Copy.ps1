param(
    [string]$InputCandidates = "",
    [switch]$NewOnly
)

$Root = Split-Path -Parent $PSScriptRoot
$Registry = Join-Path $PSScriptRoot "strategy_registry.py"
if ($InputCandidates -eq "") {
    $InputCandidates = Join-Path $Root "quant\candidate_pool.csv"
}
$Output = Join-Path $Root "quant\candidate_pool_new.csv"

Write-Host ""
Write-Host "Strategy Discovery Registry" -ForegroundColor Cyan
Write-Host "This remembers combinations across searches."
Write-Host ""

$args = @($Registry, "--input", $InputCandidates, "--output", $Output)
if ($NewOnly) { $args += "--new-only" }

python @args
if ($LASTEXITCODE -ne 0) {
    Write-Error "Registry step failed with exit code $LASTEXITCODE"
    exit $LASTEXITCODE
}
