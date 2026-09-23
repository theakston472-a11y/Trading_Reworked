[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$RunPath,
    [string]$PythonPath = "",
    [int]$Workers = 4
)

$ErrorActionPreference = "Stop"
$Root = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$Run = [System.IO.Path]::GetFullPath($RunPath)
if ([string]::IsNullOrWhiteSpace($PythonPath)) {
    $PythonPath = Join-Path $Root ".venv\Scripts\python.exe"
}
if (-not (Test-Path -LiteralPath $PythonPath)) {
    throw "Python was not found: $PythonPath"
}
if ($Workers -lt 1) {
    throw "Workers must be at least 1."
}

$Deep = Join-Path $Run "deep"
$Logs = Join-Path $Run "logs"
New-Item -ItemType Directory -Force -Path $Deep, $Logs | Out-Null
$TimingRows = New-Object System.Collections.Generic.List[object]
$Symbols = @("GBPJPY", "AUDUSD")
Set-Location $Root

foreach ($Symbol in $Symbols) {
    $Data = Join-Path $Root "quant\research_symbols\$Symbol\feature_database.csv"
    $Top100 = Join-Path $Run "promotion\$Symbol\top100_candidates.csv"
    if (-not (Test-Path -LiteralPath $Data)) { throw "Missing data: $Data" }
    if (-not (Test-Path -LiteralPath $Top100)) { throw "Missing Top 100: $Top100" }

    $SymbolDeep = Join-Path $Deep $Symbol
    New-Item -ItemType Directory -Force -Path $SymbolDeep | Out-Null
    $Rows = @(Import-Csv -LiteralPath $Top100)
    for ($Worker = 1; $Worker -le $Workers; $Worker++) {
        $Chunk = @()
        for ($Index = $Worker - 1; $Index -lt $Rows.Count; $Index += $Workers) {
            $Chunk += $Rows[$Index]
        }
        $Chunk | Export-Csv -LiteralPath (Join-Path $SymbolDeep "worker_$Worker`_candidates.csv") -NoTypeInformation
    }

    $Processes = @()
    for ($Worker = 1; $Worker -le $Workers; $Worker++) {
        $Name = "$($Symbol.ToLowerInvariant())_deep_worker_$Worker"
        $Candidates = Join-Path $SymbolDeep "worker_$Worker`_candidates.csv"
        $OutBase = Join-Path $SymbolDeep "worker_$Worker`_strategy_lab.csv"
        $Database = Join-Path $SymbolDeep "worker_$Worker.sqlite"
        $Final = "$OutBase`_final.csv"
        $TopFinal = "$OutBase`_top_final.csv"
        $Periods = "$OutBase`_periods.csv"
        $Stdout = Join-Path $Logs "$Name.log"
        $Stderr = Join-Path $Logs "$Name.err.log"
        $AlreadyComplete = (
            (Test-Path -LiteralPath $Final) -and
            (Test-Path -LiteralPath $TopFinal) -and
            (Test-Path -LiteralPath $Periods) -and
            (Test-Path -LiteralPath $Stdout) -and
            (Select-String -LiteralPath $Stdout -SimpleMatch "Unique strategies passing filters" -Quiet)
        )
        if ($AlreadyComplete) {
            $TimingRows.Add([pscustomobject]@{
                symbol = $Symbol
                worker = $Worker
                seconds = 0.0
                exit_code = 0
                status = "already_complete"
            })
            Write-Host "Already complete: $Name"
            continue
        }

        $Arguments = @(
            ".\scripts\strategy_lab.py",
            "--data", $Data,
            "--candidates", $Candidates,
            "--db", $Database,
            "--out", $OutBase,
            "--rr-start", "1.0",
            "--rr-stop", "7.0",
            "--rr-step", "0.1",
            "--max-candidates", "25",
            "--max-bars", "48",
            "--max-open-trades", "5",
            "--frequency-target", "0.75",
            "--min-trades", "20",
            "--final-n", "25",
            "--entry-mode", "auto",
            "--entry-wait-bars", "6",
            "--force"
        )
        $Started = Get-Date
        $Process = Start-Process -FilePath $PythonPath -ArgumentList $Arguments `
            -WorkingDirectory $Root -RedirectStandardOutput $Stdout `
            -RedirectStandardError $Stderr -WindowStyle Hidden -PassThru
        $Processes += [pscustomobject]@{
            Name = $Name
            Symbol = $Symbol
            Worker = $Worker
            Started = $Started
            Process = $Process
            Final = $Final
            TopFinal = $TopFinal
            Periods = $Periods
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
            (Test-Path -LiteralPath $Item.Final) -and
            (Test-Path -LiteralPath $Item.TopFinal) -and
            (Test-Path -LiteralPath $Item.Periods) -and
            (Test-Path -LiteralPath $Item.Stdout) -and
            (Select-String -LiteralPath $Item.Stdout -SimpleMatch "Unique strategies passing filters" -Quiet)
        )
        if ([string]::IsNullOrWhiteSpace([string]$ExitCode) -and $CompletedOk) {
            $ExitCode = 0
        }
        $TimingRows.Add([pscustomobject]@{
            symbol = $Item.Symbol
            worker = $Item.Worker
            seconds = [math]::Round($Seconds, 3)
            exit_code = $ExitCode
            status = if ($CompletedOk) { "complete" } else { "failed" }
        })
        Write-Host "Finished $($Item.Name): exit $ExitCode, $([math]::Round($Seconds, 1)) seconds"
        if (-not $CompletedOk -or $ExitCode -ne 0) {
            throw "Deep test failed for $($Item.Name). See $Logs"
        }
    }
}

$TimingRows | Export-Csv -LiteralPath (Join-Path $Run "deep_timings.csv") -NoTypeInformation
Write-Host "DEEP TEST COMPLETE"
Write-Host "Run folder: $Run"
