[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidateSet('Get', 'Post', 'Patch', 'Put', 'Delete')]
    [string]$Method,

    [Parameter(Mandatory = $true)]
    [ValidateNotNullOrEmpty()]
    [string]$Endpoint,

    [string]$BodyJson,

    [string]$BodyPath,

    [ValidatePattern('^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$')]
    [string]$Repository
)

$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest

function Get-GitConfigValue {
    param([Parameter(Mandatory = $true)][string]$Key)

    $value = & git config --get $Key 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($value)) {
        throw "Missing $Key. Run ./scripts/configure-github-app-git-attribution.ps1 first."
    }

    return ($value -join '').Trim()
}

function ConvertTo-Base64Url {
    param([Parameter(Mandatory = $true)][byte[]]$Bytes)

    return [Convert]::ToBase64String($Bytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

if (-not [string]::IsNullOrWhiteSpace($BodyJson) -and -not [string]::IsNullOrWhiteSpace($BodyPath)) {
    throw 'Specify either BodyJson or BodyPath, not both.'
}

if ([string]::IsNullOrWhiteSpace($Repository)) {
    $Repository = & git config --get 'aiagent.githubApp.repository' 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]::IsNullOrWhiteSpace($Repository)) {
        throw 'Missing aiagent.githubApp.repository. Run ./scripts/configure-github-app-git-attribution.ps1 first, or pass -Repository.'
    }
    $Repository = ($Repository -join '').Trim()
}

$repositoryEndpoint = "/repos/$Repository"
if ($Endpoint -ne $repositoryEndpoint -and -not $Endpoint.StartsWith("$repositoryEndpoint/", [StringComparison]::OrdinalIgnoreCase)) {
    throw "Endpoint must target $repositoryEndpoint."
}

$AppId = Get-GitConfigValue -Key 'aiagent.githubApp.appId'
$InstallationId = Get-GitConfigValue -Key 'aiagent.githubApp.installationId'
$PrivateKeyPath = Get-GitConfigValue -Key 'aiagent.githubApp.privateKeyPath'

if ($AppId -notmatch '^[0-9]+$' -or $InstallationId -notmatch '^[0-9]+$') {
    throw 'The stored GitHub App IDs are invalid.'
}

$resolvedPrivateKey = (Resolve-Path -LiteralPath $PrivateKeyPath).Path
$privateKey = [IO.File]::ReadAllText($resolvedPrivateKey)
$now = [DateTimeOffset]::UtcNow.ToUnixTimeSeconds()
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
$repositoryName = $Repository.Split('/', 2)[1]
$tokenRequestBody = @{ repositories = @($repositoryName) } | ConvertTo-Json -Compress
$tokenResponse = Invoke-RestMethod `
    -Method Post `
    -Uri "https://api.github.com/app/installations/$InstallationId/access_tokens" `
    -Headers @{
        Accept = 'application/vnd.github+json'
        Authorization = "Bearer $jwt"
        'User-Agent' = 'AI-Agent-GitHub-App-API'
        'X-GitHub-Api-Version' = '2026-03-10'
    } `
    -ContentType 'application/json' `
    -Body $tokenRequestBody

if ([string]::IsNullOrWhiteSpace($tokenResponse.token)) {
    throw 'GitHub did not return an installation access token.'
}

$requestBody = $BodyJson
if (-not [string]::IsNullOrWhiteSpace($BodyPath)) {
    $resolvedBodyPath = (Resolve-Path -LiteralPath $BodyPath).Path
    $requestBody = [IO.File]::ReadAllText($resolvedBodyPath)
}

$request = @{
    Method = $Method
    Uri = "https://api.github.com$Endpoint"
    Headers = @{
        Accept = 'application/vnd.github+json'
        Authorization = "Bearer $($tokenResponse.token)"
        'User-Agent' = 'AI-Agent-GitHub-App-API'
        'X-GitHub-Api-Version' = '2026-03-10'
    }
}

if (-not [string]::IsNullOrWhiteSpace($requestBody)) {
    $request.ContentType = 'application/json'
    $request.Body = $requestBody
}

$response = Invoke-RestMethod @request
if ($null -ne $response) {
    ConvertTo-Json -InputObject $response -Depth 100
}
