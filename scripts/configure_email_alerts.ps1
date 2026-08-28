$ErrorActionPreference = "Stop"
$project = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stateDirectory = Join-Path $project "results\alpha_mt5_paper"
$configPath = Join-Path $stateDirectory "email_config.json"
$credentialPath = Join-Path $stateDirectory "email_credentials.xml"
$senderScript = Join-Path $PSScriptRoot "send_paper_bot_email.ps1"

New-Item -ItemType Directory -Path $stateDirectory -Force | Out-Null
$sender = (Read-Host "Sender email address (Gmail or Yahoo)").Trim()
if ([string]::IsNullOrWhiteSpace($sender)) {
    throw "Sender email cannot be empty."
}
if ($sender -match "@gmail\.com$") {
    $provider = "Gmail"
    $smtpHost = "smtp.gmail.com"
}
elseif ($sender -match "@yahoo\.[a-z.]+$") {
    $provider = "Yahoo"
    $smtpHost = "smtp.mail.yahoo.com"
}
else {
    throw "Only Gmail and Yahoo sender addresses are currently supported."
}
$recipient = (Read-Host "Alert recipient email (press Enter to use the same address)").Trim()
if ([string]::IsNullOrWhiteSpace($recipient)) {
    $recipient = $sender
}
$appPassword = Read-Host "Paste the $provider app password (hidden)" -AsSecureString
$temporaryCredential = New-Object System.Management.Automation.PSCredential($sender, $appPassword)
$normalizedPassword = $temporaryCredential.GetNetworkCredential().Password -replace "\s", ""
if ([string]::IsNullOrWhiteSpace($normalizedPassword)) {
    throw "Yahoo app password cannot be empty."
}
$protectedPassword = ConvertTo-SecureString $normalizedPassword -AsPlainText -Force
$credential = New-Object System.Management.Automation.PSCredential($sender, $protectedPassword)
$normalizedPassword = $null
$credential | Export-Clixml -LiteralPath $credentialPath -Force

[ordered]@{
    smtp_host = $smtpHost
    smtp_port = 587
    sender = $sender
    recipient = $recipient
} | ConvertTo-Json | Set-Content -LiteralPath $configPath -Encoding UTF8

Write-Host "$provider email settings saved securely for this Windows user and VPS."
& $senderScript -Subject "Paper Bot - Email Test" -Body @"
Your VPS paper-bot email monitoring is configured.

Sender: $sender
Recipient: $recipient
This is a paper-only bot and does not place broker orders.
"@
Write-Host "Check the recipient inbox for the test message."
