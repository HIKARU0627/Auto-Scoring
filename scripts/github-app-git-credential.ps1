[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+$')]
    [string]$AppId,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[0-9]+$')]
    [string]$InstallationId,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$PrivateKeyPath,

    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')]
    [string]$Repository,

    [Parameter(Mandatory = $true, Position = 0)]
    [ValidateSet('get', 'store', 'erase', 'validate')]
    [string]$Operation
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

if ($Operation -in @('store', 'erase')) {
    exit 0
}

$credentialInput = @{}
if ($Operation -eq 'get') {
    while ($null -ne ($line = [Console]::In.ReadLine()) -and $line.Length -gt 0) {
        $separator = $line.IndexOf('=')
        if ($separator -gt 0) {
            $credentialInput[$line.Substring(0, $separator)] = $line.Substring($separator + 1)
        }
    }
}

if ($credentialInput.ContainsKey('host') -and $credentialInput.host -ne 'github.com') {
    exit 0
}

if ($credentialInput.ContainsKey('path')) {
    $requestedPath = $credentialInput.path.TrimEnd('/') -replace '\.git$', ''
    if ($requestedPath -ne $Repository) {
        exit 0
    }
}

$resolvedPrivateKey = (Resolve-Path -LiteralPath $PrivateKeyPath).Path
$privateKey = [System.IO.File]::ReadAllText($resolvedPrivateKey)
$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()

function ConvertTo-Base64Url {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)

    return [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$headerJson = @{ alg = 'RS256'; typ = 'JWT' } | ConvertTo-Json -Compress
$payloadJson = @{ iat = $now - 60; exp = $now + 540; iss = $AppId } | ConvertTo-Json -Compress
$header = ConvertTo-Base64Url -Bytes ([Text.Encoding]::UTF8.GetBytes($headerJson))
$payload = ConvertTo-Base64Url -Bytes ([Text.Encoding]::UTF8.GetBytes($payloadJson))
$unsignedToken = "$header.$payload"

$rsa = [Security.Cryptography.RSA]::Create()
try {
    $rsa.ImportFromPem($privateKey)
    $signatureBytes = $rsa.SignData(
        [Text.Encoding]::UTF8.GetBytes($unsignedToken),
        [Security.Cryptography.HashAlgorithmName]::SHA256,
        [Security.Cryptography.RSASignaturePadding]::Pkcs1
    )
}
finally {
    $rsa.Dispose()
}

$jwt = "$unsignedToken.$(ConvertTo-Base64Url -Bytes $signatureBytes)"
if ($Operation -eq 'validate') {
    Write-Output 'JWT signing succeeded; no installation access token requested.'
    exit 0
}

$repositoryName = $Repository.Split('/', 2)[1]
$requestBody = @{
    repositories = @($repositoryName)
    permissions = @{ contents = 'write'; workflows = 'write' }
} | ConvertTo-Json -Compress

$response = Invoke-RestMethod `
    -Method Post `
    -Uri "https://api.github.com/app/installations/$InstallationId/access_tokens" `
    -Headers @{
        Accept = 'application/vnd.github+json'
        Authorization = "Bearer $jwt"
        'User-Agent' = 'AI-Agent-GitHub-App-Git-Credential'
        'X-GitHub-Api-Version' = '2026-03-10'
    } `
    -ContentType 'application/json' `
    -Body $requestBody

if ([string]::IsNullOrWhiteSpace($response.token)) {
    throw 'GitHub did not return an installation access token.'
}

Write-Output 'protocol=https'
Write-Output 'host=github.com'
Write-Output 'username=x-access-token'
Write-Output "password=$($response.token)"
Write-Output ''
