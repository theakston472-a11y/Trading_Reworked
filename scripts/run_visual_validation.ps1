param([string]$Pool="london_sell")

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python -m pipeline --skip-discovery --pool $Pool
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
