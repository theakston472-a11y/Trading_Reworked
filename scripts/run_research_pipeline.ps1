param(
    [switch]$SkipDiscovery,
    [switch]$SkipDeep,
    [switch]$SkipVisual,
    [string[]]$Pool
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

$args = @("-m", "pipeline")
if ($SkipDiscovery) { $args += "--skip-discovery" }
if ($SkipDeep) { $args += "--skip-deep" }
if ($SkipVisual) { $args += "--skip-visual" }
if ($Pool) {
    foreach($p in $Pool) { $args += @("--pool", $p) }
}

python @args
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
