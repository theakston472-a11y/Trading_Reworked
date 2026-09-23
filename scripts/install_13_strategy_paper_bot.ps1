param(
    [string]$ProjectRoot = "C:\Trading_Reworked",
    [string]$SourceCommit = "742f073"
)

$ErrorActionPreference = "Stop"
$project = [System.IO.Path]::GetFullPath($ProjectRoot)
$python = Join-Path $project ".venv\Scripts\python.exe"
$statePath = Join-Path $project "results\alpha_mt5_paper\state.json"
$startScript = Join-Path $project "scripts\start_alpha_paper_bot.ps1"

if (-not (Test-Path -LiteralPath $project -PathType Container)) {
    throw "Project folder not found: $project"
}
if (-not (Test-Path -LiteralPath $python -PathType Leaf)) {
    throw "Paper-bot Python environment not found: $python"
}
if (-not (Test-Path -LiteralPath $statePath -PathType Leaf)) {
    throw "Paper-bot state file not found: $statePath"
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $project "archive\paper_bot_before_13_$stamp"
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) "paper_bot_13_$([guid]::NewGuid().ToString('N'))"
$rawRoot = "https://raw.githubusercontent.com/theakston472-a11y/Trading_Reworked/$SourceCommit"
$files = @(
    "paper_bot_strategies.csv",
    "scripts/alpha_mt5_paper_bot.py",
    "scripts/email_latest_signal_chart.py",
    "scripts/start_alpha_paper_bot.ps1"
)

New-Item -ItemType Directory -Path $temporary -Force | Out-Null
New-Item -ItemType Directory -Path (Join-Path $temporary "scripts") -Force | Out-Null

try {
    foreach ($relative in $files) {
        $destination = Join-Path $temporary $relative
        Invoke-WebRequest -UseBasicParsing -Uri "$rawRoot/$relative" -OutFile $destination
        if (-not (Test-Path -LiteralPath $destination -PathType Leaf)) {
            throw "Download failed: $relative"
        }
    }

    & $python -m py_compile `
        (Join-Path $temporary "scripts\alpha_mt5_paper_bot.py") `
        (Join-Path $temporary "scripts\email_latest_signal_chart.py")
    if ($LASTEXITCODE -ne 0) {
        throw "The downloaded Python files did not compile."
    }

    $running = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*alpha_mt5_paper_bot.py*" -and $_.Name -like "python*" }
    )
    foreach ($process in $running) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
    }

    New-Item -ItemType Directory -Path (Join-Path $backup "scripts") -Force | Out-Null
    foreach ($relative in $files) {
        $current = Join-Path $project $relative
        if (Test-Path -LiteralPath $current -PathType Leaf) {
            $backupFile = Join-Path $backup $relative
            Copy-Item -LiteralPath $current -Destination $backupFile -Force
        }
    }

    foreach ($relative in $files) {
        Copy-Item -LiteralPath (Join-Path $temporary $relative) -Destination (Join-Path $project $relative) -Force
    }

    Push-Location $project
    try {
        & $python "scripts\alpha_mt5_paper_bot.py" --self-test
        if ($LASTEXITCODE -ne 0) {
            throw "The multi-symbol paper-bot self-test failed."
        }
        & $python "scripts\email_latest_signal_chart.py" --self-test
        if ($LASTEXITCODE -ne 0) {
            throw "The signal-chart self-test failed."
        }
        & $startScript
    }
    finally {
        Pop-Location
    }

    Start-Sleep -Seconds 10
    $started = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*alpha_mt5_paper_bot.py*" -and $_.Name -like "python*" }
    )
    if ($started.Count -eq 0) {
        throw "The updated files passed their tests, but the paper-bot process did not remain running."
    }

    Write-Host "13-strategy paper bot installed and started."
    Write-Host "PID: $($started[0].ProcessId)"
    Write-Host "Existing state preserved: $statePath"
    Write-Host "Backup: $backup"
}
catch {
    $installError = $_
    if (Test-Path -LiteralPath $backup -PathType Container) {
        foreach ($relative in $files) {
            $backupFile = Join-Path $backup $relative
            if (Test-Path -LiteralPath $backupFile -PathType Leaf) {
                Copy-Item -LiteralPath $backupFile -Destination (Join-Path $project $relative) -Force
            }
        }
        try {
            & $startScript
            Write-Warning "The previous paper bot files were restored and restarted."
        }
        catch {
            Write-Warning "The previous files were restored, but their automatic restart also failed."
        }
    }
    throw $installError
}
finally {
    if (Test-Path -LiteralPath $temporary -PathType Container) {
        Remove-Item -LiteralPath $temporary -Recurse -Force
    }
}
