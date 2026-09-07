#Requires -Version 7.0
<#
.SYNOPSIS
    Boots a packaged sidecar executable and proves it actually works.

.DESCRIPTION
    The acceptance test for `backend/packaging/auto-scoring-sidecar.spec`.
    PyInstaller cannot fail a build for an import it did not find -- a missing
    hidden import, data file or native library only surfaces when the frozen
    executable runs, on a machine with no Python installed. This script is
    that run, and CI fails on it before any artifact is uploaded.

    It exercises exactly what the Flutter supervisor does
    (`app/lib/core/sidecar_supervisor.dart`) plus the two things a unit test
    cannot check about a *packaged* build:

      1. `--self-test`, which imports the lazily-loaded native-backed modules
         (OpenCV, pdfium, reportlab) that a plain boot never touches.
      2. A real boot: handshake -> /healthz -> an authenticated call -> an
         unauthenticated call is refused -> terminate -> the port is free and
         no process is left behind.

.PARAMETER SidecarPath
    The packaged executable, e.g. backend/dist/auto-scoring-sidecar/auto-scoring-sidecar.exe

.PARAMETER TimeoutSeconds
    How long to wait for the sidecar to become healthy. Generous by default:
    the first launch runs every schema migration against a new database, and
    Windows Defender scans a freshly built, unsigned executable tree.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SidecarPath,

    [int]$TimeoutSeconds = 180
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step([string]$Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

if (-not (Test-Path -LiteralPath $SidecarPath)) {
    throw "sidecar executable not found: $SidecarPath"
}
$SidecarPath = (Resolve-Path -LiteralPath $SidecarPath).Path

# Everything this script creates lives here and is removed at the end, so a
# smoke test never touches the runner's real per-user app-data location.
$workDir = Join-Path ([System.IO.Path]::GetTempPath()) "sidecar-smoke-$(New-Guid)"
New-Item -ItemType Directory -Path $workDir -Force | Out-Null
$handshakeFile = Join-Path $workDir 'handshake.json'
$appDataDir = Join-Path $workDir 'app-data'

$process = $null
try {
    Write-Step 'Verifying the bundle can import every native-backed dependency'
    # Separate from the boot below on purpose: OpenCV, pdfium and reportlab are
    # imported lazily, on the first answer PDF, so a bundle missing one of them
    # boots and serves /healthz perfectly well and only fails later, in front
    # of a user.
    & $SidecarPath --self-test
    if ($LASTEXITCODE -ne 0) {
        throw "--self-test failed with exit code $LASTEXITCODE"
    }

    Write-Step 'Starting the packaged sidecar on a dynamic port'
    $stdoutFile = Join-Path $workDir 'stdout.log'
    $stderrFile = Join-Path $workDir 'stderr.log'
    $process = Start-Process -FilePath $SidecarPath -PassThru -NoNewWindow `
        -RedirectStandardOutput $stdoutFile -RedirectStandardError $stderrFile `
        -ArgumentList @(
            '--port', '0',
            '--handshake-file', $handshakeFile,
            '--app-data-dir', $appDataDir
        )

    Write-Step "Waiting up to ${TimeoutSeconds}s for the handshake"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $handshake = $null
    while ($null -eq $handshake) {
        if ($process.HasExited) {
            throw "sidecar exited during startup with code $($process.ExitCode)"
        }
        if ((Get-Date) -gt $deadline) {
            throw "sidecar never wrote a complete handshake within ${TimeoutSeconds}s"
        }
        # Success is "parses into a complete host/port/token", never "the file
        # exists" -- the same rule the Flutter supervisor applies, because the
        # file is created before it is written.
        if (Test-Path -LiteralPath $handshakeFile) {
            try {
                $candidate = Get-Content -LiteralPath $handshakeFile -Raw | ConvertFrom-Json
                if ($candidate.host -and $candidate.port -and $candidate.token) {
                    $handshake = $candidate
                    break
                }
            } catch {
                # Partial write; try again.
            }
        }
        Start-Sleep -Milliseconds 250
    }

    $port = [int]$handshake.port
    $baseUrl = "http://$($handshake.host):$port"
    # The port, never the token: this output goes into a public CI log.
    Write-Host "    handshake: $baseUrl (token redacted)"
    if ($handshake.host -ne '127.0.0.1') {
        throw "sidecar bound $($handshake.host), expected loopback only"
    }

    Write-Step 'Waiting for /healthz'
    $healthy = $false
    while (-not $healthy) {
        if ($process.HasExited) {
            throw "sidecar exited before becoming healthy with code $($process.ExitCode)"
        }
        if ((Get-Date) -gt $deadline) {
            throw "sidecar never answered /healthz within ${TimeoutSeconds}s"
        }
        try {
            $health = Invoke-RestMethod -Uri "$baseUrl/healthz" -TimeoutSec 5
            if ($health.status -eq 'ok') { $healthy = $true; break }
        } catch {
            # Not listening yet.
        }
        Start-Sleep -Milliseconds 250
    }

    Write-Step 'Calling a protected endpoint with the session token'
    $scored = Invoke-RestMethod -Uri "$baseUrl/score" -Method Post -TimeoutSec 10 `
        -Headers @{ Authorization = "Bearer $($handshake.token)" } `
        -ContentType 'application/json' `
        -Body '{"key":"q1","raw":15,"maximum":10}'
    if ($scored.awarded -ne 10) {
        throw "unexpected /score response: awarded=$($scored.awarded)"
    }

    Write-Step 'Confirming the same endpoint refuses an unauthenticated call'
    # A packaged build that silently lost its auth dependency would still pass
    # every check above.
    $status = 0
    try {
        Invoke-WebRequest -Uri "$baseUrl/score" -Method Post -TimeoutSec 10 `
            -ContentType 'application/json' `
            -Body '{"key":"q1","raw":1,"maximum":10}' | Out-Null
    } catch {
        $status = [int]$_.Exception.Response.StatusCode
    }
    if ($status -ne 401) {
        throw "unauthenticated /score returned $status, expected 401"
    }

    Write-Step 'Confirming the database was created and migrated'
    $database = Join-Path $appDataDir 'database.sqlite'
    if (-not (Test-Path -LiteralPath $database)) {
        throw "no database at $database -- alembic migrations did not run in the bundle"
    }

    Write-Step 'Confirming the sidecar wrote its own rotating log'
    $log = Join-Path $appDataDir 'logs\sidecar.log'
    if (-not (Test-Path -LiteralPath $log)) {
        throw "no log at $log"
    }
    if (Select-String -LiteralPath $log -SimpleMatch -Pattern $handshake.token -Quiet) {
        throw 'the session token leaked into the log file'
    }

    Write-Step 'Terminating, and checking nothing is left behind'
    $pid = $process.Id
    $process.Kill()
    if (-not $process.WaitForExit(30000)) {
        throw "sidecar did not exit within 30s of being killed"
    }
    if (Get-Process -Id $pid -ErrorAction SilentlyContinue) {
        throw "process $pid survived termination"
    }

    # Nothing answers on that port any more. Probed rather than re-bound: a
    # just-closed listener's port can still be refused by `bind` while the
    # connections above sit in TIME_WAIT, which says nothing about whether a
    # process survived.
    $stillServing = $false
    try {
        Invoke-RestMethod -Uri "$baseUrl/healthz" -TimeoutSec 3 | Out-Null
        $stillServing = $true
    } catch {
        # Expected: connection refused.
    }
    if ($stillServing) {
        throw "something is still serving on port $port after the sidecar exited"
    }

    Write-Host ''
    Write-Host 'Sidecar smoke test passed.' -ForegroundColor Green
} catch {
    Write-Host ''
    Write-Host 'Sidecar smoke test FAILED.' -ForegroundColor Red
    foreach ($name in 'stdout.log', 'stderr.log') {
        $path = Join-Path $workDir $name
        if (Test-Path -LiteralPath $path) {
            Write-Host "--- $name ---"
            Get-Content -LiteralPath $path -Tail 200
        }
    }
    throw
} finally {
    if ($null -ne $process -and -not $process.HasExited) {
        $process.Kill()
        $process.WaitForExit(10000) | Out-Null
    }
    Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
}
