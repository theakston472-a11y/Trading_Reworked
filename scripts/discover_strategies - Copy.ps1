param([int]$MaxConditions=4,[int]$MaxNew=5000,[int]$MinTrades=20,[double]$QuickRR=2.0,[int]$MaxOpenTrades=5,[string]$Session="New York",[string]$Direction="SELL")
$Root=Split-Path -Parent $PSScriptRoot
python (Join-Path $PSScriptRoot "strategy_discovery.py") --max-conditions $MaxConditions --max-new $MaxNew --min-trades $MinTrades --rr $QuickRR --max-open $MaxOpenTrades --session $Session --direction $Direction
if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
