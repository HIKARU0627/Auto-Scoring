#Requires -Version 7.0
<#
.SYNOPSIS
    Boots the packaged Electron desktop application and validates end-to-end
    invariants (Issue #265).

.DESCRIPTION
    Acceptance tests for the packaged Electron desktop application:
      1. UI & Data Rendering Test:
         Boots the packaged application using Playwright, verifies that the
         sidecar reaches 'ready', that real data is rendered from the sidecar
         API (home-next-up visible), and that no home-error is displayed.
      2. Orphan Sidecar Prevention Test (UG-01/02, Issue #211):
         Boots the packaged application, discovers the child sidecar process
         and listening port, performs a forced termination of the Electron
         parent process (Task Manager End Task simulation), and validates that
         the Python parent watchdog terminates the sidecar within its detection
         budget (leaving no orphan process) and that the port is released.

.PARAMETER AppPath
    Path to the packaged Electron application executable.
    Defaults to:
      - Windows: desktop/dist/win-unpacked/Auto-Scoring.exe
      - Linux: desktop/dist/linux-unpacked/auto-scoring

.PARAMETER TimeoutSeconds
    Overall timeout in seconds for startup and probes (default: 180).

.PARAMETER SkipUiTest
    Skips the Playwright UI rendering check and runs only the orphan kill test.
#>
[CmdletBinding()]
param(
    [string]$AppPath,
    [int]$TimeoutSeconds = 180,
    [switch]$SkipUiTest
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step([string]$Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

$repoRoot = Split-Path -Parent $PSScriptRoot

if (-not $AppPath) {
    if ($IsWindows) {
        $AppPath = Join-Path $repoRoot 'desktop\dist\win-unpacked\Auto-Scoring.exe'
    } else {
        $AppPath = Join-Path $repoRoot 'desktop/dist/linux-unpacked/auto-scoring'
        if (-not (Test-Path -LiteralPath $AppPath)) {
            $AppPath = Join-Path $repoRoot 'desktop/dist/linux-unpacked/@auto-scoringdesktop'
        }
    }
}

if (-not (Test-Path -LiteralPath $AppPath)) {
    throw "Packaged application executable not found at: $AppPath. Did you run 'pnpm run package:electron'?"
}
$AppPath = (Resolve-Path -LiteralPath $AppPath).Path
Write-Host "Testing packaged application at: $AppPath" -ForegroundColor Green

# -----------------------------------------------------------------------------
# Part 1: UI & Data Rendering Test (Acceptance Criterion 3)
# -----------------------------------------------------------------------------
if (-not $SkipUiTest) {
    Write-Step 'Part 1: Verifying packaged app boots, sidecar reaches ready, and real data is rendered'
    $env:PACKAGED_APP_PATH = $AppPath
    try {
        $desktopDir = Join-Path $repoRoot 'desktop'
        Push-Location $desktopDir
        pnpm exec playwright test e2e/smoke-packaged.spec.ts
        if ($LASTEXITCODE -ne 0) {
            throw "Packaged app Playwright smoke test failed ($LASTEXITCODE)"
        }
    } finally {
        Pop-Location
        $env:PACKAGED_APP_PATH = $null
    }
    Write-Host 'Part 1 PASSED: Packaged app rendered real data without home-error.' -ForegroundColor Green
} else {
    Write-Host 'Part 1: UI test skipped by switch.' -ForegroundColor Yellow
}

# -----------------------------------------------------------------------------
# Part 2: Forced Termination & Orphan Sidecar Prevention Test (Acceptance Criterion 4)
# -----------------------------------------------------------------------------
Write-Step 'Part 2: Testing force-kill orphan sidecar prevention'

$appArgs = @(
    '--no-sandbox'
)
if (-not $IsWindows) {
    $appArgs += '--ozone-platform=x11'
}

$stdoutFile = Join-Path ([System.IO.Path]::GetTempPath()) "electron-smoke-stdout-$(New-Guid).log"
$stderrFile = Join-Path ([System.IO.Path]::GetTempPath()) "electron-smoke-stderr-$(New-Guid).log"

$electronProc = $null
$sidecarPid = $null
$port = $null

try {
    Write-Step 'Starting packaged application for orphan test'
    $electronProc = Start-Process -FilePath $AppPath -WorkingDirectory (Split-Path -Parent $AppPath) -ArgumentList $appArgs -PassThru -NoNewWindow `
        -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile

    $parentPid = $electronProc.Id
    Write-Host "    Electron process PID: $parentPid"

    Write-Step 'Locating sidecar child process spawned with --parent-pid'
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline -and $null -eq $sidecarPid) {
        if ($electronProc.HasExited) {
            throw "Electron process exited prematurely with code $($electronProc.ExitCode)"
        }
        if ($IsWindows) {
            $found = Get-CimInstance Win32_Process | Where-Object {
                $_.CommandLine -like "*--parent-pid $parentPid*"
            } | Select-Object -First 1
            if ($found) { $sidecarPid = [int]$found.ProcessId }
        } else {
            $out = pgrep -f -- "--parent-pid $parentPid"
            if ($out) {
                $pids = $out -split "\s+"
                if ($pids.Count -gt 0 -and $pids[0]) {
                    $sidecarPid = [int]$pids[0]
                }
            }
        }
        if ($null -eq $sidecarPid) { Start-Sleep -Milliseconds 250 }
    }

    if ($null -eq $sidecarPid) {
        throw "Could not locate sidecar child process with --parent-pid $parentPid within ${TimeoutSeconds}s"
    }
    Write-Host "    Sidecar child process PID: $sidecarPid"

    Write-Step 'Discovering sidecar listening port'
    $portDeadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $portDeadline -and $null -eq $port) {
        if ($IsWindows) {
            $conn = Get-NetTCPConnection -OwningProcess $sidecarPid -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
            if ($conn) { $port = [int]$conn.LocalPort }
        } else {
            $ss = ss -tlnp 2>$null | Select-String "pid=$sidecarPid"
            if ($ss) {
                if ($ss.Line -match ":(\d+)\s+") {
                    $port = [int]$Matches[1]
                }
            }
        }
        if ($null -eq $port) { Start-Sleep -Milliseconds 250 }
    }

    if ($null -eq $port) {
        throw "Could not determine sidecar listening port for PID $sidecarPid"
    }
    Write-Host "    Sidecar listening on port: $port"

    Write-Step "Probing http://127.0.0.1:$port/healthz"
    # 60s, not the bare 30 this used to be: the same budget the shipped Electron
    # supervisor allows this sidecar to become ready
    # (`SIDECAR_STARTUP_TIMEOUT_MS` in desktop/src/main/sidecar-supervisor.ts),
    # so the smoke test waits exactly as long as the product does.
    #
    # Why 30 was not enough (Issue #399): a Windows CI run found this sidecar's
    # pid 0.5s after launch and its listening port ~3s in -- the same timings a
    # *passing* run shows -- and /healthz still had not answered when the old
    # 30s deadline expired. The OS reports a port as `Listen` only after uvicorn
    # has called listen(), which happens after ASGI startup, so the script was
    # not probing an unready port: the second sidecar had reached serving and
    # its HTTP response stalled. That is the same undiagnosed loopback stall
    # already recorded for this product on Windows
    # (docs/answer-intake-and-preprocessing.md section 22,
    # docs/windows-distribution.md section 7.3); the remedy there was a
    # realistic budget plus evidence on the next failure, which is what the
    # probe log below adds. No fixed sleep: the loop still polls.
    $healthBudgetSeconds = 60
    $probeStartedAt = Get-Date
    $healthDeadline = $probeStartedAt.AddSeconds($healthBudgetSeconds)
    $healthy = $false
    $probeResponses = [System.Collections.Generic.List[string]]::new()
    while ((Get-Date) -lt $healthDeadline) {
        # Fail fast, and name which process died, rather than spend the whole
        # budget on a port nothing can answer on.
        if ($electronProc.HasExited) {
            throw "Electron process exited during the health probe with code $($electronProc.ExitCode)"
        }
        if (-not (Get-Process -Id $sidecarPid -ErrorAction SilentlyContinue)) {
            throw "Sidecar process $sidecarPid exited during the health probe"
        }

        $elapsedSeconds = [int](((Get-Date) - $probeStartedAt).TotalSeconds)
        try {
            $res = Invoke-RestMethod -Uri "http://127.0.0.1:$port/healthz" -TimeoutSec 3
            if ($res.status -eq "ok") {
                $healthy = $true
                break
            }
            $probeResponses.Add("${elapsedSeconds}s: 2xx but status='$($res.status)'")
            Start-Sleep -Milliseconds 250
        } catch {
            # The message is what tells a refusal (nobody listening on the port)
            # apart from a timeout (listening, but no HTTP response): the two
            # failures this probe exists to distinguish. First line only -- the
            # nested exception text under it repeats the same thing.
            $reason = ($_.Exception.Message -split "`r?`n")[0]
            $probeResponses.Add("${elapsedSeconds}s: $reason")
            Start-Sleep -Milliseconds 250
        }
    }
    if (-not $healthy) {
        $waitedSeconds = [math]::Round(((Get-Date) - $probeStartedAt).TotalSeconds, 1)
        # What the next failure needs in the log: how long was spent, what each
        # probe actually got back, and whether the two processes were even
        # still alive -- three questions that cost a person a run to answer
        # when #399 struck.
        Write-Host "    /healthz on port $port never became healthy: waited ${waitedSeconds}s of a ${healthBudgetSeconds}s budget." -ForegroundColor Red
        Write-Host "    $($probeResponses.Count) probe attempt(s), in order:" -ForegroundColor Red
        foreach ($response in $probeResponses) {
            Write-Host "      $response" -ForegroundColor Red
        }
        Write-Host "    Electron process ${parentPid} alive: $(-not $electronProc.HasExited)" -ForegroundColor Red
        Write-Host "    Sidecar process ${sidecarPid} alive: $([bool](Get-Process -Id $sidecarPid -ErrorAction SilentlyContinue))" -ForegroundColor Red
        throw "Sidecar at port $port did not return healthy status before kill"
    }
    Write-Host '    Sidecar is healthy and serving.'

    Write-Step "Simulating Task Manager End Task (force-killing Electron parent PID $parentPid)"
    if ($IsWindows) {
        Stop-Process -Id $parentPid -Force
    } else {
        kill -9 $parentPid
    }

    Write-Step 'Waiting for Python parent watchdog to detect parent termination and exit (budget: 15s)'
    $watchDeadline = (Get-Date).AddSeconds(15)
    $sidecarDead = $false
    while ((Get-Date) -lt $watchDeadline) {
        $p = Get-Process -Id $sidecarPid -ErrorAction SilentlyContinue
        if ($null -eq $p -or $p.HasExited) {
            $sidecarDead = $true
            break
        }
        Start-Sleep -Milliseconds 250
    }

    if (-not $sidecarDead) {
        throw "Sidecar (PID $sidecarPid) survived after parent process was killed! Watchdog failed."
    }
    Write-Host "    Sidecar process $sidecarPid exited cleanly." -ForegroundColor Green

    Write-Step 'Verifying port was released'
    $portFreed = $false
    $probeDeadline = (Get-Date).AddSeconds(10)
    while ((Get-Date) -lt $probeDeadline) {
        try {
            Invoke-RestMethod -Uri "http://127.0.0.1:$port/healthz" -TimeoutSec 2 | Out-Null
            Start-Sleep -Milliseconds 250
        } catch {
            $portFreed = $true
            break
        }
    }

    if (-not $portFreed) {
        throw "Port $port is still responding after sidecar exited!"
    }
    Write-Host "    Port $port was successfully released." -ForegroundColor Green
    Write-Host 'Part 2 PASSED: Orphan sidecar was cleanly terminated and port released.' -ForegroundColor Green
    Write-Host ''
    Write-Host 'Packaged Electron application smoke test completed successfully!' -ForegroundColor Green
} finally {
    # Emergency cleanup
    if ($null -ne $sidecarPid) {
        Stop-Process -Id $sidecarPid -Force -ErrorAction SilentlyContinue
    }
    if ($null -ne $electronProc -and -not $electronProc.HasExited) {
        Stop-Process -Id $electronProc.Id -Force -ErrorAction SilentlyContinue
    }
    Remove-Item -LiteralPath $stdoutFile -Force -ErrorAction SilentlyContinue
    Remove-Item -LiteralPath $stderrFile -Force -ErrorAction SilentlyContinue
}
