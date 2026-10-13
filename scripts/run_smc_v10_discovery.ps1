[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunPath,
    [string]$FeatureRoot = "",
    [string]$ScratchPath = "",
    [string]$PythonPath = "",
    [string[]]$Symbols = @("GBPUSD", "GBPJPY", "AUDUSD"),
    [string[]]$Sessions = @("Asia", "London", "New York"),
    [int]$MaxNew = 5000,
    [int]$MaxExamined = 200000
)

$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Run = [System.IO.Path]::GetFullPath($RunPath)
$FeatureBase = if ([string]::IsNullOrWhiteSpace($FeatureRoot)) {
    Join-Path $Run "features"
} else {
    [System.IO.Path]::GetFullPath($FeatureRoot)
}
$Work = if ([string]::IsNullOrWhiteSpace($ScratchPath)) {
    $Run
} else {
    [System.IO.Path]::GetFullPath($ScratchPath)
}
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $Root ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $PythonPath)) { throw "Python was not found: $PythonPath" }
if ($MaxNew -lt 1) { throw "MaxNew must be at least 1." }
if ($MaxExamined -lt 1) { throw "MaxExamined must be at least 1." }

$Discovery = Join-Path $Work "discovery"
$Logs = Join-Path $Work "logs"
New-Item -ItemType Directory -Force -Path $Discovery,$Logs | Out-Null
$Rows = New-Object System.Collections.Generic.List[object]
Set-Location $Root

foreach ($Session in $Sessions) {
    $Processes = @()
    foreach ($Symbol in $Symbols) {
        $Data = Join-Path $FeatureBase "$Symbol\feature_database.csv"
        if (-not (Test-Path -LiteralPath $Data)) { throw "Missing V10 feature database: $Data" }
        foreach ($Direction in @("BUY", "SELL")) {
            $SessionKey = $Session.ToLowerInvariant() -replace " ", "_"
            $Name = "$($Symbol.ToLowerInvariant())_${SessionKey}_$($Direction.ToLowerInvariant())"
            $Output = Join-Path $Discovery "$Name.csv"
            $Registry = Join-Path $Discovery "$Name.sqlite"
            $Stdout = Join-Path $Logs "$Name.log"
            $Stderr = Join-Path $Logs "$Name.err.log"
            $AlreadyComplete = (
                (Test-Path -LiteralPath $Output) -and
                (Test-Path -LiteralPath $Stdout) -and
                (Select-String -LiteralPath $Stdout -SimpleMatch "DISCOVERY COMPLETE" -Quiet)
            )
            if ($AlreadyComplete) {
                $Rows.Add([pscustomobject]@{
                    symbol=$Symbol; session=$Session; direction=$Direction;
                    seconds=0.0; exit_code=0; status="already_complete"
                })
                Write-Host "Already complete: $Name"
                continue
            }
            if ((Test-Path -LiteralPath $Output) -or (Test-Path -LiteralPath $Registry)) {
                throw "Refusing to replace an existing discovery scan: $Name"
            }
            $SessionArgument = if ($Session.Contains(" ")) { '"' + $Session + '"' } else { $Session }
            $Arguments = @(
                ".\scripts\strategy_discovery.py",
                "--data", $Data,
                "--db", $Registry,
                "--out", $Output,
                "--direction", $Direction,
                "--session", $SessionArgument,
                "--max-conditions", "4",
                "--min-trades", "20",
                "--max-new", [string]$MaxNew,
                "--max-examined", [string]$MaxExamined,
                "--rr", "2.0",
                "--max-open", "5",
                "--max-bars", "48",
                "--entry-mode", "auto",
                "--entry-wait-bars", "6"
            )
            $Started = Get-Date
            $Process = Start-Process -FilePath $PythonPath -ArgumentList $Arguments `
                -WorkingDirectory $Root -RedirectStandardOutput $Stdout `
                -RedirectStandardError $Stderr -WindowStyle Hidden -PassThru
            $Processes += [pscustomobject]@{
                Name=$Name; Symbol=$Symbol; Session=$Session; Direction=$Direction;
                Started=$Started; Process=$Process; Output=$Output; Stdout=$Stdout; Stderr=$Stderr
            }
            Write-Host "Started $Name (PID $($Process.Id))"
        }
    }
    if ($Processes.Count -eq 0) {
        continue
    }
    $Processes.Process | Wait-Process
    foreach ($Item in $Processes) {
        $Item.Process.Refresh()
        $Seconds = ((Get-Date) - $Item.Started).TotalSeconds
        $Complete = (
            ($Item.Process.ExitCode -eq 0) -and
            (Test-Path -LiteralPath $Item.Output) -and
            (Select-String -LiteralPath $Item.Stdout -SimpleMatch "DISCOVERY COMPLETE" -Quiet)
        )
        $Rows.Add([pscustomobject]@{
            symbol=$Item.Symbol; session=$Item.Session; direction=$Item.Direction;
            seconds=[math]::Round($Seconds,3); exit_code=$Item.Process.ExitCode;
            status=if ($Complete) { "complete" } else { "failed" }
        })
        Write-Host "Finished $($Item.Name): exit $($Item.Process.ExitCode), $([math]::Round($Seconds,1)) seconds"
        if (-not $Complete) {
            Get-Content -LiteralPath $Item.Stderr -Tail 60 -ErrorAction SilentlyContinue
            throw "Discovery failed for $($Item.Name)."
        }
    }
}

$Timing = Join-Path $Work "discovery_timings.csv"
$Rows | Export-Csv -LiteralPath $Timing -NoTypeInformation
if ($Work -ne $Run) {
    $TargetDiscovery = Join-Path $Run "discovery"
    $TargetLogs = Join-Path $Run "logs"
    if ((Test-Path -LiteralPath $TargetDiscovery) -or (Test-Path -LiteralPath $TargetLogs)) {
        throw "Refusing to replace an existing target discovery/log folder in $Run"
    }
    New-Item -ItemType Directory -Force -Path $Run,$TargetDiscovery,$TargetLogs | Out-Null
    Copy-Item -Path (Join-Path $Discovery "*") -Destination $TargetDiscovery
    Copy-Item -Path (Join-Path $Logs "*") -Destination $TargetLogs
    Copy-Item -LiteralPath $Timing -Destination (Join-Path $Run "discovery_timings.csv")
}
Write-Host "DISCOVERY COMPLETE"
Write-Host "Run folder: $Run"
Write-Host "Timings: $Timing"
