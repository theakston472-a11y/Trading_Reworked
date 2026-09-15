[CmdletBinding()]
param(
    [string]$ProjectRoot = "C:\Trading_Reworked"
)

$ErrorActionPreference = "Stop"
$branch = "feature/paperbot-signal-chart-email-20260915"
$baseUrl = "https://raw.githubusercontent.com/theakston472-a11y/Trading_Reworked/$branch/scripts"
$scriptDirectory = Join-Path $ProjectRoot "scripts"
$python = Join-Path $ProjectRoot ".venv\Scripts\python.exe"
$startScript = Join-Path $scriptDirectory "start_alpha_paper_bot.ps1"
$timestamp = Get-Date -Format "yyyyMMdd_HHmmss"
$backupDirectory = Join-Path $ProjectRoot "results\deployment_backups\signal_chart_email_$timestamp"
$temporaryRoot = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
$temporaryDirectory = Join-Path $temporaryRoot ("paperbot_signal_chart_" + [guid]::NewGuid().ToString("N"))
$fileNames = @(
    "alpha_mt5_paper_bot.py",
    "paper_bot_email.py",
    "send_paper_bot_email.ps1",
    "email_latest_signal_chart.py"
)
$requiredExistingFiles = @(
    "alpha_mt5_paper_bot.py",
    "paper_bot_email.py",
    "send_paper_bot_email.ps1"
)
$originalFiles = @{}
$backedUp = $false
$installed = $false

if (-not (Test-Path -LiteralPath $scriptDirectory)) {
    throw "Project scripts folder was not found: $scriptDirectory"
}
if (-not (Test-Path -LiteralPath $python)) {
    throw "Paper-bot Python environment was not found: $python"
}

New-Item -ItemType Directory -Path $temporaryDirectory -Force | Out-Null
try {
    foreach ($fileName in $fileNames) {
        $downloadPath = Join-Path $temporaryDirectory $fileName
        Invoke-WebRequest -UseBasicParsing -Uri "$baseUrl/$fileName" -OutFile $downloadPath
        if ((Get-Item -LiteralPath $downloadPath).Length -lt 100) {
            throw "Downloaded file is unexpectedly small: $fileName"
        }
    }

    $downloadedBot = Join-Path $temporaryDirectory "alpha_mt5_paper_bot.py"
    $downloadedEmail = Join-Path $temporaryDirectory "paper_bot_email.py"
    $downloadedSender = Join-Path $temporaryDirectory "send_paper_bot_email.ps1"
    $downloadedBackfill = Join-Path $temporaryDirectory "email_latest_signal_chart.py"
    if (-not (Select-String -LiteralPath $downloadedBot -SimpleMatch "def save_signal_chart" -Quiet)) {
        throw "Downloaded bot does not contain the signal-chart feature."
    }
    if (-not (Select-String -LiteralPath $downloadedEmail -SimpleMatch "attachment_path" -Quiet)) {
        throw "Downloaded email helper does not contain attachment support."
    }
    if (-not (Select-String -LiteralPath $downloadedSender -SimpleMatch "AttachmentPath" -Quiet)) {
        throw "Downloaded email sender does not contain attachment support."
    }

    & $python -B -m py_compile $downloadedBot $downloadedEmail $downloadedBackfill
    if ($LASTEXITCODE -ne 0) {
        throw "Python validation failed."
    }
    $tokens = $null
    $parseErrors = $null
    [void][System.Management.Automation.Language.Parser]::ParseFile(
        $downloadedSender, [ref]$tokens, [ref]$parseErrors
    )
    if ($parseErrors.Count -gt 0) {
        throw "PowerShell validation failed: $($parseErrors[0].Message)"
    }

    New-Item -ItemType Directory -Path $backupDirectory -Force | Out-Null
    foreach ($fileName in $requiredExistingFiles) {
        $target = Join-Path $scriptDirectory $fileName
        if (-not (Test-Path -LiteralPath $target)) {
            throw "Existing VPS file was not found: $target"
        }
    }
    foreach ($fileName in $fileNames) {
        $target = Join-Path $scriptDirectory $fileName
        $originalFiles[$fileName] = Test-Path -LiteralPath $target
        if ($originalFiles[$fileName]) {
            Copy-Item -LiteralPath $target -Destination (Join-Path $backupDirectory $fileName)
        }
    }
    $backedUp = $true

    $botProcesses = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*alpha_mt5_paper_bot.py*" -and $_.Name -like "python*" })
    foreach ($process in $botProcesses) {
        Stop-Process -Id $process.ProcessId -Force -ErrorAction Stop
    }
    if ($botProcesses.Count -gt 0) {
        Start-Sleep -Seconds 2
    }

    $installed = $true
    foreach ($fileName in $fileNames) {
        Copy-Item -LiteralPath (Join-Path $temporaryDirectory $fileName) `
            -Destination (Join-Path $scriptDirectory $fileName) -Force
    }
    & $startScript
    Start-Sleep -Seconds 5
    $running = @(Get-CimInstance Win32_Process -ErrorAction SilentlyContinue |
        Where-Object { $_.CommandLine -like "*alpha_mt5_paper_bot.py*" -and $_.Name -like "python*" })
    if ($running.Count -eq 0) {
        throw "The updated paper bot did not remain running."
    }

    Write-Host "SIGNAL CHART EMAILS READY"
    Write-Host "Paper bot PID: $($running[0].ProcessId)"
    Write-Host "Backup folder: $backupDirectory"
}
catch {
    $failure = $_.Exception.Message
    if ($installed -and $backedUp) {
        Write-Warning "Update failed; restoring the previous paper-bot files."
        foreach ($fileName in $fileNames) {
            $target = Join-Path $scriptDirectory $fileName
            if ($originalFiles[$fileName]) {
                Copy-Item -LiteralPath (Join-Path $backupDirectory $fileName) `
                    -Destination $target -Force
            }
            elseif (Test-Path -LiteralPath $target) {
                Remove-Item -LiteralPath $target -Force
            }
        }
        try {
            & $startScript
        }
        catch {
            Write-Warning "Previous bot could not be restarted automatically: $($_.Exception.Message)"
        }
    }
    throw $failure
}
finally {
    $resolvedTemporary = [System.IO.Path]::GetFullPath($temporaryDirectory)
    if ($resolvedTemporary.StartsWith($temporaryRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolvedTemporary)) {
        Remove-Item -LiteralPath $resolvedTemporary -Recurse -Force
    }
}
