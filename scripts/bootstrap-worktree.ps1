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

# Restore the Flutter app packages from app/pubspec.lock.
$appDir = Join-Path $repoRoot 'app'
if ((Test-Path (Join-Path $appDir 'pubspec.yaml')) -and (Get-Command flutter -ErrorAction SilentlyContinue)) {
    Push-Location $appDir
    try { flutter pub get } finally { Pop-Location }
}
elseif (Test-Path (Join-Path $appDir 'pubspec.yaml')) {
    Write-Host 'Skipping flutter pub get (flutter not on PATH). See app/.fvmrc for the pinned version.'
}

# Restore the Python sidecar environment from backend/uv.lock.
$backendDir = Join-Path $repoRoot 'backend'
if ((Test-Path (Join-Path $backendDir 'uv.lock')) -and (Get-Command uv -ErrorAction SilentlyContinue)) {
    Push-Location $backendDir
    try { uv sync --locked } finally { Pop-Location }
}
elseif (Test-Path (Join-Path $backendDir 'uv.lock')) {
    Write-Host 'Skipping uv sync (uv not on PATH). Install uv: https://docs.astral.sh/uv/'
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

# `core.hooksPath` alone does not mean the hooks run. Git skips a hook file that
# is not executable and says so only as a hint on stderr, so a worktree can look
# fully bootstrapped while every hook is dead -- which is exactly where this
# repository sat until Issue #75 (both hooks tracked as 100644, never fired).
# Check the tracked mode, which is what every clone gets, and on POSIX the
# checked-out file as well, because that is the bit git actually tests before
# running a hook. Fail instead of warn: a warning is what let this go unnoticed.
$brokenHooks = @()
foreach ($hook in Get-ChildItem -Path (Join-Path $repoRoot '.githooks') -File) {
    $path = ".githooks/$($hook.Name)"
    $trackedMode = ((& git ls-files --stage -- $path | Out-String).Trim() -split '\s+')[0]

    if ([string]::IsNullOrEmpty($trackedMode)) {
        $brokenHooks += "$path is not tracked by git; run: git add $path"
    }
    elseif ($trackedMode -ne '100755') {
        $brokenHooks += "$path is tracked as $trackedMode; run: git update-index --chmod=+x $path"
    }
    # Git decides whether to run a hook with access(X_OK). Windows ignores X_OK
    # there, so the on-disk bit only matters -- and only exists -- on POSIX.
    elseif (-not $IsWindows -and ($hook.UnixFileMode -band [System.IO.UnixFileMode]::UserExecute) -eq 0) {
        $brokenHooks += "$path is not executable in this worktree; run: chmod +x $path"
    }
}
if ($brokenHooks.Count -gt 0) {
    throw ("git hooks are not executable, so git would silently skip them:`n  " +
        ($brokenHooks -join "`n  ") + "`nSee docs/quality-gates.md 'git hooks vs CI'.")
}

Write-Host 'Bootstrap completed.'
