param([int]$MaxOpenTrades=5,[int]$MinTrades=20,[double]$FrequencyTarget=0.75,[switch]$Charts,[switch]$Force)
$Root=Split-Path -Parent $PSScriptRoot;$c=Join-Path $Root "quant\top100_candidates.csv"
if(-not(Test-Path $c)){Write-Error "Top-100 file not found. Run .\scripts\promote_top100.ps1 first.";exit 1}
$args=@((Join-Path $PSScriptRoot "strategy_lab.py"),"--candidates",$c,"--max-candidates","100","--rr-start","1.0","--rr-stop","7.0","--rr-step","0.1","--max-open-trades",$MaxOpenTrades,"--min-trades",$MinTrades,"--frequency-target",$FrequencyTarget,"--final-n","20");if($Charts){$args+="--charts"};if($Force){$args+="--force"};python @args;if($LASTEXITCODE -ne 0){exit $LASTEXITCODE}
