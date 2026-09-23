[CmdletBinding()]
param(
    [string]$PythonPath = "",
    [int]$MaxNew = 5000,
    [string]$RunPath = ""
)

$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $Root ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Python was not found: $PythonPath"
}
if ($MaxNew -lt 1) {
    throw "MaxNew must be at least 1."
}

$Stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$Run = if ([string]::IsNullOrWhiteSpace($RunPath)) {
    Join-Path $Root "results\research_symbols\runs\$Stamp"
} else {
    [System.IO.Path]::GetFullPath($RunPath)
}
$Discovery = Join-Path $Run "discovery"
$Logs = Join-Path $Run "logs"
New-Item -ItemType Directory -Force -Path $Discovery, $Logs | Out-Null
Set-Content -LiteralPath (Join-Path $Root "results\research_symbols\latest_run.txt") -Value $Run

$Rows = New-Object System.Collections.Generic.List[object]
$Symbols = @("GBPJPY", "AUDUSD")
$Sessions = @("Asia", "London", "New York")
$Directions = @("BUY", "SELL")

Set-Location $Root

foreach ($Symbol in $Symbols) {
    $Data = Join-Path $Root "quant\research_symbols\$Symbol\feature_database.csv"
    if (-not (Test-Path -LiteralPath $Data)) {
        throw "Feature database is missing: $Data"
    }
    foreach ($Session in $Sessions) {
        $Pool = ($Session.ToLowerInvariant() -replace " ", "_")
        $SessionArgument = if ($Session.Contains(" ")) { '"' + $Session + '"' } else { $Session }
        $Processes = @()
        foreach ($Direction in $Directions) {
            $Name = "$($Symbol.ToLowerInvariant())_${Pool}_$($Direction.ToLowerInvariant())"
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
                    symbol = $Symbol
                    session = $Session
                    direction = $Direction
                    seconds = 0.0
                    exit_code = 0
                    status = "already_complete"
                })
                Write-Host "Already complete: $Name"
                continue
            }
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
                Name = $Name
                Symbol = $Symbol
                Session = $Session
                Direction = $Direction
                Started = $Started
                Process = $Process
                Output = $Output
                Stdout = $Stdout
            }
            Write-Host "Started $Name (PID $($Process.Id))"
        }

        foreach ($Item in $Processes) {
            $Item.Process.WaitForExit()
            $Item.Process.Refresh()
            $Finished = Get-Date
            $Seconds = ($Finished - $Item.Started).TotalSeconds
            $ExitCode = $Item.Process.ExitCode
            $CompletedOk = (
                (Test-Path -LiteralPath $Item.Output) -and
                (Test-Path -LiteralPath $Item.Stdout) -and
                (Select-String -LiteralPath $Item.Stdout -SimpleMatch "DISCOVERY COMPLETE" -Quiet)
            )
            if ([string]::IsNullOrWhiteSpace([string]$ExitCode) -and $CompletedOk) {
                $ExitCode = 0
            }
            $Rows.Add([pscustomobject]@{
                symbol = $Item.Symbol
                session = $Item.Session
                direction = $Item.Direction
                seconds = [math]::Round($Seconds, 3)
                exit_code = $ExitCode
                status = if ($CompletedOk) { "complete" } else { "failed" }
            })
            Write-Host "Finished $($Item.Name): exit $ExitCode, $([math]::Round($Seconds, 1)) seconds"
            if (-not $CompletedOk -or $ExitCode -ne 0) {
                throw "Discovery failed for $($Item.Name). See $Logs"
            }
        }
    }
}

$Timing = Join-Path $Run "discovery_timings.csv"
$Rows | Export-Csv -LiteralPath $Timing -NoTypeInformation
Write-Host "DISCOVERY COMPLETE"
Write-Host "Run folder: $Run"
Write-Host "Timings: $Timing"
