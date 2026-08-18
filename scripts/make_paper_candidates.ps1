$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

python -m pipeline.paper_candidates
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
