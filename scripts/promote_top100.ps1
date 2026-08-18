param([string]$Input="",[int]$TopN=100)

$Root=Split-Path -Parent $PSScriptRoot

if($Input -eq "") {
    $Input=Join-Path $Root "results\discovery_all.csv"
}

$out=Join-Path $Root "quant\top100_candidates.csv"

python (Join-Path $PSScriptRoot "promote_top100.py") --input $Input --output $out --top $TopN

if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
