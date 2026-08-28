$ErrorActionPreference = "Stop"
$project = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stateDirectory = Join-Path $project "results\alpha_mt5_paper"
$configPath = Join-Path $stateDirectory "email_config.json"
$credentialPath = Join-Path $stateDirectory "email_credentials.xml"
$senderScript = Join-Path $PSScriptRoot "send_paper_bot_email.ps1"

New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
$sender = (Read-Host "Yahoo sender email address").Trim()
if ([string]::IsNullOrWhiteSpace($sender)) {
    throw "Sender email cannot be empty."
}
$recipient = (Read-Host "Alert recipient email (press Enter to use the same address)").Trim()
if ([string]::IsNullOrWhiteSpace($recipient)) {
    $recipient = $sender
}
$appPassword = Read-Host "Paste the Yahoo app password (hidden)" -AsSecureString
$credential = New-Object System.Management.Automation.PSCredential($sender, $appPassword)
$credential | Export-Clixml -LiteralPath $credentialPath -Force

[ordered]@{
    smtp_host = "smtp.mail.yahoo.com"
    smtp_port = 587
    sender = $sender
    recipient = $recipient
} | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8

Write-Host "Yahoo email settings saved securely for this Windows user and VPS."
& $senderScript -Subject "Paper Bot - Email Test" -Body @"
Your VPS paper-bot email monitoring is configured.

Sender: $sender
Recipient: $recipient
This is a paper-only bot and does not place broker orders.
"@
Write-Host "Check the recipient inbox for the test message."

