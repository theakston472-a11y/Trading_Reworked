param(
    [string]$ProjectRoot = "C:\Trading_Reworked",
    [string]$SourceCommit = "eccaefa"
)

$ErrorActionPreference = "Stop"
$project = [System.IO.Path]::GetFullPath($ProjectRoot)
$python = Join-Path $project ".venv\Scripts\python.exe"
$statePath = Join-Path $project "results\alpha_mt5_paper\state.json"
$healthPath = Join-Path $project "results\alpha_mt5_paper\health.json"
$startScript = Join-Path $project "scripts\start_alpha_paper_bot.ps1"

foreach ($required in @($project, $python, $statePath, $startScript)) {
    if (-not (Test-Path -LiteralPath $required)) {
        throw "Required paper-bot path not found: $required"
    }
}

$stamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backup = Join-Path $project "archive\paper_bot_before_phase_fix_$stamp"
$temporary = Join-Path ([System.IO.Path]::GetTempPath()) "paper_bot_phase_fix_$([guid]::NewGuid().ToString('N'))"
$rawRoot = "https://raw.githubusercontent.com/theakston472-a11y/Trading_Reworked/$SourceCommit"
$files = @(
    "scripts/alpha_mt5_paper_bot.py",
    "scripts/paper_bot_email.py"
)

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
        (Join-Path $temporary "scripts\paper_bot_email.py")
    if ($LASTEXITCODE -ne 0) {
        throw "The downloaded phase-transition update did not compile."
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
            Copy-Item -LiteralPath $current -Destination (Join-Path $backup $relative) -Force
        }
    }
    Copy-Item -LiteralPath $statePath -Destination (Join-Path $backup "state.json") -Force

    foreach ($relative in $files) {
        Copy-Item -LiteralPath (Join-Path $temporary $relative) -Destination (Join-Path $project $relative) -Force
    }

    Push-Location $project
    try {
        & $python "scripts\alpha_mt5_paper_bot.py" --self-test
        if ($LASTEXITCODE -ne 0) {
            throw "The automatic phase-transition self-test failed."
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

    Write-Host "Automatic phase transition installed and the paper bot restarted."
    Write-Host "PID: $($started[0].ProcessId)"
    Write-Host "Existing state preserved and upgraded: $statePath"
    Write-Host "Backup: $backup"
    if (Test-Path -LiteralPath $healthPath -PathType Leaf) {
        Get-Content -LiteralPath $healthPath
    }
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
            Write-Warning "The previous bot files were restored and restarted."
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
