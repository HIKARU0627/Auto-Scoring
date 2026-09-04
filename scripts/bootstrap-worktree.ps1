[CmdletBinding()]
param(
    # Skip the GitHub App attribution step even if it is configured.
    [switch]$NoGithubApp
)

$ErrorActionPreference = 'Stop'
$PSNativeCommandUseErrorActionPreference = $true
Set-StrictMode -Version Latest

$repoRoot = (& git rev-parse --show-toplevel).Trim()
Set-Location $repoRoot

# GitHub App attribution is opt-in. It runs only after the shared Git config holds
# the App settings (first run: ./scripts/configure-github-app-git-attribution.ps1
# with all parameters). Projects that let agents commit from a personal account
# can ignore this step.
# `git config --get` exits non-zero when the key is unset; keep that from
# aborting the script under the strict native-error preference above.
$appConfigured = ''
try {
    $appConfigured = (& git config --get 'aiagent.githubApp.appId' 2>$null | Out-String).Trim()
}
catch {
    $appConfigured = ''
}
if (-not $NoGithubApp -and -not [string]::IsNullOrWhiteSpace($appConfigured)) {
    & (Join-Path $PSScriptRoot 'configure-github-app-git-attribution.ps1')
}
else {
    Write-Host 'Skipping GitHub App attribution (not configured). See docs/ai-agent-git-attribution.md.'
}

if (Get-Command corepack -ErrorAction SilentlyContinue) {
    corepack enable
}

if (Test-Path (Join-Path $repoRoot 'pnpm-lock.yaml')) {
    pnpm install --frozen-lockfile
}
else {
    pnpm install
}

# Point git at the tracked hooks. Prefer worktree-scoped config (Orca worktrees
# enable extensions.worktreeConfig), but fall back to repo-scoped so a plain
# `git clone` also works.
$worktreeConfig = ''
try {
    $worktreeConfig = (& git config --get extensions.worktreeConfig 2>$null | Out-String).Trim()
}
catch {
    $worktreeConfig = ''
}
if ($worktreeConfig -eq 'true') {
    git config --worktree core.hooksPath .githooks
}
else {
    git config core.hooksPath .githooks
}

Write-Host 'Bootstrap completed.'
