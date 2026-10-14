param(
    [string]$ProjectRoot = "C:\Trading_Reworked",
    [string]$SourceCommit = "5325da5"
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
$backup = Join-Path $project "archive\paper_bot_before_v10_gj05_$stamp"
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) "paper_bot_v10_gj05_$([guid]::NewGuid().ToString('N'))"
$rawRoot = "https://raw.githubusercontent.com/theakston472-a11y/Trading_Reworked/$SourceCommit"
$files = @(
    "paper_bot_strategies.csv",
    "quant/feature_engine.py",
    "quant/smc_guide_features.py",
    "scripts/alpha_mt5_paper_bot.py",
    "scripts/paper_bot_email.py",
    "scripts/email_latest_signal_chart.py",
    "scripts/start_alpha_paper_bot.ps1",
    "scripts/verify_smc_guide_features.py"
)

New-Item -ItemType Directory -Path $temporary -Force | Out-Null

try {
    foreach ($relative in $files) {
        $destination = Join-Path $temporary $relative
        New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
        Invoke-WebRequest -UseBasicParsing -Uri "$rawRoot/$relative" -OutFile $destination
        if (-not (Test-Path -LiteralPath $destination -PathType Leaf)) {
            throw "Download failed: $relative"
        }
    }

    $strategies = @(Import-Csv (Join-Path $temporary "paper_bot_strategies.csv"))
    $gj05 = @($strategies | Where-Object {
        $_.strategy_id -eq "GJ05" -and
        $_.symbol -eq "GBPJPY" -and
        $_.direction -eq "BUY" -and
        $_.session -eq "New York" -and
        $_.conditions -eq "above_ema200+bullish_choch+new_york_kill_zone" -and
        [double]$_.rr -eq 3.0
    })
    if ($strategies.Count -ne 14 -or $gj05.Count -ne 1) {
        throw "Downloaded strategy plan is not the verified 14-strategy GJ05 plan."
    }

    & $python -m py_compile `
        (Join-Path $temporary "quant\feature_engine.py") `
        (Join-Path $temporary "quant\smc_guide_features.py") `
        (Join-Path $temporary "scripts\alpha_mt5_paper_bot.py") `
        (Join-Path $temporary "scripts\paper_bot_email.py") `
        (Join-Path $temporary "scripts\email_latest_signal_chart.py") `
        (Join-Path $temporary "scripts\verify_smc_guide_features.py")
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

    foreach ($relative in $files) {
        $current = Join-Path $project $relative
        if (Test-Path -LiteralPath $current -PathType Leaf) {
            $backupFile = Join-Path $backup $relative
            New-Item -ItemType Directory -Path (Split-Path $backupFile -Parent) -Force | Out-Null
            Copy-Item -LiteralPath $current -Destination $backupFile -Force
        }
    }

    foreach ($relative in $files) {
        $destination = Join-Path $project $relative
        New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
        Copy-Item -LiteralPath (Join-Path $temporary $relative) -Destination $destination -Force
    }

    Push-Location $project
    try {
        & $python "scripts\verify_smc_guide_features.py"
        if ($LASTEXITCODE -ne 0) {
            throw "The V10 SMC feature verification failed."
        }
        & $python "scripts\alpha_mt5_paper_bot.py" --self-test
        if ($LASTEXITCODE -ne 0) {
            throw "The 14-strategy paper-bot self-test failed."
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

    Start-Sleep -Seconds 12
    $started = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*alpha_mt5_paper_bot.py*" -and $_.Name -like "python*" }
    )
    if ($started.Count -eq 0) {
        throw "The updated files passed their tests, but the paper-bot process did not remain running."
    }

    Write-Host "14-strategy V10 paper bot installed and started."
    Write-Host "Added: GJ05 GBPJPY BUY New York RR3."
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
                $destination = Join-Path $project $relative
                New-Item -ItemType Directory -Path (Split-Path $destination -Parent) -Force | Out-Null
                Copy-Item -LiteralPath $backupFile -Destination $destination -Force
            }
        }
        try {
            & $startScript
            Write-Warning "The previous paper-bot files were restored and restarted."
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
