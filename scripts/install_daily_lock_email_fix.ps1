param(
    [string]$ProjectRoot = "C:\Trading_Reworked",
    [string]$SourceCommit = "8b43be1"
)

$ErrorActionPreference = "Stop"
$project = [System.IO.Path]::GetFullPath($ProjectRoot)
$python = Join-Path $project ".venv\Scripts\python.exe"
$statePath = Join-Path $project "results\alpha_mt5_paper\state.json"
$startScript = Join-Path $project "scripts\start_alpha_paper_bot.ps1"
$relative = "scripts/alpha_mt5_paper_bot.py"

foreach ($required in @($project, $python, $statePath, $startScript)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required paper-bot path not found: $required"
    }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $project "archive\paper_bot_before_daily_email_fix_$stamp"
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) "paper_bot_daily_email_fix_$([guid]::NewGuid().ToString('N'))"
$download = Join-Path $temporary "alpha_mt5_paper_bot.py"
$current = Join-Path $project "scripts\alpha_mt5_paper_bot.py"
$rawUrl = "https://raw.githubusercontent.com/theakston472-a11y/Trading_Reworked/$SourceCommit/$relative"

New-Item -ItemType Directory -Path $temporary -Force | Out-Null

try {
    Invoke-WebRequest -UseBasicParsing -Uri $rawUrl -OutFile $download
    & $python -m py_compile $download
    if ($LASTEXITCODE -ne 0) {
        throw "The downloaded daily-lock fix did not compile."
    }

    $running = @(
        Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
            Where-Object { $_.CommandLine -like "*alpha_mt5_paper_bot.py*" -and $_.Name -like "python*" }
    )
    foreach ($process in $running) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
    }

    New-Item -ItemType Directory -Path $backup -Force | Out-Null
    Copy-Item -LiteralPath $current -Destination (Join-Path $backup "alpha_mt5_paper_bot.py") -Force
    Copy-Item -LiteralPath $statePath -Destination (Join-Path $backup "state.json") -Force
    Copy-Item -LiteralPath $download -Destination $current -Force

    Push-Location $project
    try {
        & $python "scripts\alpha_mt5_paper_bot.py" --self-test
        if ($LASTEXITCODE -ne 0) {
            throw "The daily-lock email self-test failed."
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
        throw "The updated paper bot did not remain running."
    }

    Write-Host "Daily-limit email fix installed."
    Write-Host "The existing daily lock remains active, but only one lock email is sent per breach."
    Write-Host "PID: $($started[0].ProcessId)"
    Write-Host "Backup: $backup"
}
catch {
    $installError = $_
    $backupFile = Join-Path $backup "alpha_mt5_paper_bot.py"
    if (Test-Path -LiteralPath $backupFile -PathType Leaf) {
        Copy-Item -LiteralPath $backupFile -Destination $current -Force
        try {
            & $startScript
            Write-Warning "The previous paper bot was restored and restarted."
        }
        catch {
            Write-Warning "The previous file was restored, but its automatic restart failed."
        }
    }
    throw $installError
}
finally {
    if (Test-Path -LiteralPath $temporary -PathType Container) {
        Remove-Item -LiteralPath $temporary -Recurse -Force
    }
}
