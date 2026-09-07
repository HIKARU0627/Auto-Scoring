#Requires -Version 7.0
<#
.SYNOPSIS
    Compiles the unsigned Windows installer from the two builds that must
    already exist.

.DESCRIPTION
    Wraps Inno Setup's compiler (ISCC.exe), which is not on PATH even on the
    images that ship it, and installs it through Chocolatey when it is absent.

    The output is deliberately **unsigned** (see `installer/auto-scoring.iss`
    and `docs/windows-distribution.md` §8): no certificate, key or signing
    credential belongs in this repository or in CI. Signing is a separate,
    human-only step performed on the artifact this produces.

.PARAMETER Configuration
    Which Flutter build output to package. `Release` (default) is what ships;
    `Debug` exists so a developer can package a debug build without editing
    the .iss.
#>
[CmdletBinding()]
param(
    [ValidateSet('Release', 'Debug')]
    [string]$Configuration = 'Release'
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

$repoRoot = Split-Path -Parent $PSScriptRoot
$script = Join-Path $repoRoot 'installer\auto-scoring.iss'
$flutterOutput = Join-Path $repoRoot "app\build\windows\x64\runner\$Configuration"
$sidecarOutput = Join-Path $repoRoot 'backend\dist\auto-scoring-sidecar'

# Checked here rather than left to Inno Setup, whose "no files found matching"
# error names a wildcard rather than the build step that was skipped.
if (-not (Test-Path -LiteralPath (Join-Path $flutterOutput 'auto_scoring_app.exe'))) {
    throw "No Flutter $Configuration build at $flutterOutput. Run: cd app; flutter build windows --$($Configuration.ToLower())"
}
if (-not (Test-Path -LiteralPath (Join-Path $sidecarOutput 'auto-scoring-sidecar.exe'))) {
    throw "No packaged sidecar at $sidecarOutput. Run: pnpm run package:sidecar"
}

function Resolve-Iscc {
    $onPath = Get-Command 'iscc.exe' -ErrorAction SilentlyContinue
    if ($onPath) { return $onPath.Source }
    foreach ($candidate in @(
            "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
            "$env:ProgramFiles\Inno Setup 6\ISCC.exe"
        )) {
        if ($candidate -and (Test-Path -LiteralPath $candidate)) { return $candidate }
    }
    return $null
}

$iscc = Resolve-Iscc
if (-not $iscc) {
    Write-Host 'Inno Setup not found; installing it with Chocolatey...' -ForegroundColor Yellow
    choco install innosetup -y --no-progress
    if ($LASTEXITCODE -ne 0) { throw "choco install innosetup failed ($LASTEXITCODE)" }
    $iscc = Resolve-Iscc
    if (-not $iscc) { throw 'Inno Setup installed but ISCC.exe was still not found' }
}

Write-Host "Compiling $script with $iscc" -ForegroundColor Cyan
# /Qp: quiet but still print errors. The .iss resolves its own source paths
# relative to itself, so it is compiled from its own directory.
& $iscc '/Qp' $script
if ($LASTEXITCODE -ne 0) { throw "ISCC failed with exit code $LASTEXITCODE" }

$output = Join-Path $repoRoot 'installer\output'
Get-ChildItem -LiteralPath $output -Filter '*.exe' | ForEach-Object {
    Write-Host "Built $($_.FullName) ($([math]::Round($_.Length / 1MB, 1)) MB, unsigned)" -ForegroundColor Green
}
