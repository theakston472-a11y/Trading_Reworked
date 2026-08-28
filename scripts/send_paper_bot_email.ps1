[CmdletBinding()]
param(
    [string]$Subject,
    [string]$Body,
    [string]$PayloadPath
)

$ErrorActionPreference = "Stop"
$project = [System.IO.Path]::GetFullPath((Join-Path $PSScriptRoot ".."))
$stateDirectory = Join-Path $project "results\alpha_mt5_paper"
$configPath = Join-Path $stateDirectory "email_config.json"
$credentialPath = Join-Path $stateDirectory "email_credentials.xml"

if (-not (Test-Path -LiteralPath $configPath)) {
    throw "Email configuration is missing. Run scripts\configure_email_alerts.ps1."
}
if (-not (Test-Path -LiteralPath $credentialPath)) {
    throw "Protected email credential is missing. Run scripts\configure_email_alerts.ps1."
}
if ($PayloadPath) {
    $payload = Get-Content -LiteralPath $PayloadPath -Raw | ConvertFrom-Json
    $Subject = [string]$payload.subject
    $Body = [string]$payload.body
}
if ([string]::IsNullOrWhiteSpace($Subject)) {
    throw "Email subject is empty."
}

$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$credential = Import-Clixml -LiteralPath $credentialPath
$mail = New-Object System.Net.Mail.MailMessage
$client = New-Object System.Net.Mail.SmtpClient([string]$config.smtp_host, [int]$config.smtp_port)
try {
    $mail.From = [string]$config.sender
    [void]$mail.To.Add([string]$config.recipient)
    $mail.Subject = $Subject
    $mail.Body = $Body
    $mail.IsBodyHtml = $false
    $client.EnableSsl = $true
    $client.UseDefaultCredentials = $false
    $client.Credentials = $credential.GetNetworkCredential()
    $client.Timeout = 30000
    $client.Send($mail)
    Write-Host "EMAIL SENT"
}
finally {
    $mail.Dispose()
    $client.Dispose()
}

