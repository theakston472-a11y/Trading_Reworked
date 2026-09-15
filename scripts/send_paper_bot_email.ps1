[CmdletBinding()]
param(
    [string]$Subject,
    [string]$Body,
    [string]$PayloadPath,
    [string]$AttachmentPath
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
    if ($payload.attachment_path) {
        $AttachmentPath = [string]$payload.attachment_path
    }
}
if ([string]::IsNullOrWhiteSpace($Subject)) {
    throw "Email subject is empty."
}

$config = Get-Content -LiteralPath $configPath -Raw | ConvertFrom-Json
$credential = Import-Clixml -LiteralPath $credentialPath
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$mail = [System.Net.Mail.MailMessage]::new()
$client = [System.Net.Mail.SmtpClient]::new([string]$config.smtp_host, [int]$config.smtp_port)
try {
    $mail.From = [string]$config.sender
    [void]$mail.To.Add([string]$config.recipient)
    $mail.Subject = $Subject
    $mail.Body = $Body
    $mail.IsBodyHtml = $false
    if (-not [string]::IsNullOrWhiteSpace($AttachmentPath)) {
        if (Test-Path -LiteralPath $AttachmentPath) {
            [void]$mail.Attachments.Add([System.Net.Mail.Attachment]::new($AttachmentPath))
        }
        else {
            Write-Warning "Email attachment was not found: $AttachmentPath"
        }
    }
    $client.EnableSsl = $true
    $client.UseDefaultCredentials = $false
    $client.Credentials = $credential.GetNetworkCredential()
    $client.Timeout = 30000
    $client.Send($mail)
    Write-Host "EMAIL SENT"
}
catch {
    $messages = New-Object System.Collections.Generic.List[string]
    $current = $_.Exception
    while ($null -ne $current) {
        [void]$messages.Add($current.Message)
        $current = $current.InnerException
    }
    throw "Email send failed: $($messages -join ' -> ')"
}
finally {
    $mail.Dispose()
    $client.Dispose()
}
