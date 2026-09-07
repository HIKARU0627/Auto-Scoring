#Requires -Version 7.0
<#
.SYNOPSIS
    TEMPORARY diagnostic for Issue #57. Delete once the question it answers is
    settled.

.DESCRIPTION
    Answers one question with measurements instead of guesses: when the thing
    the Flutter supervisor spawns is terminated the way `Process.kill()` does
    it (`TerminateProcess` on that pid only), is anything left alive and still
    serving the sidecar API?

    It reproduces `SidecarSupervisor._terminateCurrentProcess` exactly -- kill
    the pid that was spawned, wait for *that* process to exit, then look --
    and prints:

      * the process tree under the spawned pid while it is healthy,
      * which process actually owns the listening socket,
      * after the kill, a timeline of how long any descendant survives and how
        long the port keeps answering an authenticated request.

    Run it against both executables to tell a product problem from a
    test-harness one:

      * `backend/.venv/Scripts/auto-scoring-sidecar.exe` -- what
        `sidecar_supervisor_integration_test.dart` starts,
      * `backend/dist/auto-scoring-sidecar/auto-scoring-sidecar.exe` -- what a
        user actually runs.

.PARAMETER SidecarPath
    The sidecar executable to start.

.PARAMETER TimeoutSeconds
    How long to wait for the handshake and the first healthy response.

.PARAMETER WatchSeconds
    How long to keep sampling after the kill.

.NOTES
    Rehearsed on Linux before pushing, like `smoke-test-sidecar.ps1`: the
    Windows-only parts (`Win32_Process`, `Get-NetTCPConnection`) are guarded so
    the rest of the script's own bugs surface there.
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [string]$SidecarPath,

    [int]$TimeoutSeconds = 180,

    [int]$WatchSeconds = 30
)

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

function Write-Step([string]$Message) {
    Write-Host "==> $Message" -ForegroundColor Cyan
}

# Every descendant of $RootPid, breadth first. Windows only -- this is the
# whole point of the diagnostic, and `Win32_Process` is the only place the
# parent/child edges are visible.
function Get-DescendantProcesses([int]$RootPid) {
    if (-not $IsWindows) { return @() }
    $all = Get-CimInstance Win32_Process |
        Select-Object ProcessId, ParentProcessId, Name, CommandLine
    $found = @()
    $frontier = @($RootPid)
    while ($frontier.Count -gt 0) {
        $children = $all | Where-Object { $frontier -contains $_.ParentProcessId }
        if (-not $children) { break }
        $found += $children
        $frontier = @($children | ForEach-Object { $_.ProcessId })
    }
    return $found
}

function Test-ProtectedCall([string]$BaseUrl, [string]$Token) {
    try {
        Invoke-RestMethod -Uri "$BaseUrl/tests" -TimeoutSec 3 `
            -Headers @{ Authorization = "Bearer $Token" } | Out-Null
        return 'serving (200 with this session token)'
    } catch {
        # Not `$_.Exception.Response` directly: a refused connection raises an
        # exception type that has no such property at all, and strict mode
        # turns reading it into a terminating error.
        $exception = $_.Exception
        if ($exception.PSObject.Properties.Name -contains 'Response' -and $null -ne $exception.Response) {
            return "HTTP $([int]$exception.Response.StatusCode)"
        }
        return 'refused'
    }
}

if (-not (Test-Path -LiteralPath $SidecarPath)) {
    throw "sidecar executable not found: $SidecarPath"
}
$SidecarPath = (Resolve-Path -LiteralPath $SidecarPath).Path

$workDir = Join-Path ([System.IO.Path]::GetTempPath()) "sidecar-tree-$(New-Guid)"
New-Item -ItemType Directory -Path $workDir -Force | Out-Null
$handshakeFile = Join-Path $workDir 'handshake.json'
$appDataDir = Join-Path $workDir 'app-data'

$process = $null
$descendantPids = @()
try {
    Write-Host "Diagnosing: $SidecarPath"
    Write-Step 'Starting the sidecar on a dynamic port'
    $process = Start-Process -FilePath $SidecarPath -PassThru -NoNewWindow `
        -RedirectStandardOutput (Join-Path $workDir 'stdout.log') `
        -RedirectStandardError (Join-Path $workDir 'stderr.log') `
        -ArgumentList @(
            '--port', '0',
            '--handshake-file', "`"$handshakeFile`"",
            '--app-data-dir', "`"$appDataDir`""
        )
    $spawnedPid = $process.Id
    Write-Host "    spawned pid: $spawnedPid"

    Write-Step "Waiting up to ${TimeoutSeconds}s for the handshake and /healthz"
    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    $handshake = $null
    while ($null -eq $handshake) {
        if ($process.HasExited) { throw "sidecar exited with code $($process.ExitCode)" }
        if ((Get-Date) -gt $deadline) { throw 'no handshake in time' }
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

    $healthy = $false
    while (-not $healthy) {
        if ((Get-Date) -gt $deadline) { throw 'never became healthy' }
        try {
            if ((Invoke-RestMethod -Uri "$baseUrl/healthz" -TimeoutSec 5).status -eq 'ok') {
                $healthy = $true
                break
            }
        } catch {
            # Not listening yet.
        }
        Start-Sleep -Milliseconds 250
    }

    Write-Step 'Process tree under the spawned pid, while healthy'
    $descendants = @(Get-DescendantProcesses -RootPid $spawnedPid)
    if ($descendants.Count -eq 0) {
        Write-Host '    none -- the spawned process is the whole sidecar'
    } else {
        foreach ($d in $descendants) {
            Write-Host "    pid $($d.ProcessId) parent $($d.ParentProcessId) $($d.Name)"
            Write-Host "        $($d.CommandLine)"
        }
    }

    if ($IsWindows) {
        Write-Step 'Owner of the listening socket'
        $owners = Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue
        foreach ($owner in $owners) {
            $name = (Get-Process -Id $owner.OwningProcess -ErrorAction SilentlyContinue).ProcessName
            Write-Host "    port $port is owned by pid $($owner.OwningProcess) ($name)"
        }
    }

    Write-Step 'Killing the spawned pid, exactly as the supervisor does'
    $descendantPids = @($descendants | ForEach-Object { $_.ProcessId })
    $process.Kill()
    if (-not $process.WaitForExit(30000)) { throw 'the spawned process did not exit' }
    Write-Host ('    pid ' + $spawnedPid + ': exited -- the point the supervisor waits for')

    Write-Step "Sampling for ${WatchSeconds}s after that point"
    $watchDeadline = (Get-Date).AddSeconds($WatchSeconds)
    $started = Get-Date
    $lastLine = ''
    $clearedAt = $null
    while ($true) {
        $elapsed = ((Get-Date) - $started).TotalMilliseconds
        $alive = @($descendantPids | Where-Object {
            Get-Process -Id $_ -ErrorAction SilentlyContinue
        })
        $serving = Test-ProtectedCall -BaseUrl $baseUrl -Token $handshake.token
        $line = "descendants alive: $($alive.Count) of $($descendantPids.Count); port: $serving"
        if ($line -ne $lastLine) {
            Write-Host ("    t+{0,6:n0} ms  {1}" -f $elapsed, $line)
            $lastLine = $line
        }
        if ($alive.Count -eq 0 -and $serving -eq 'refused') {
            $clearedAt = $elapsed
            break
        }
        if ((Get-Date) -gt $watchDeadline) { break }
        Start-Sleep -Milliseconds 100
    }

    Write-Host ''
    if ($null -eq $clearedAt) {
        Write-Host "VERDICT: still not clear after ${WatchSeconds}s -- a real orphan." -ForegroundColor Red
    } elseif ($clearedAt -lt 1) {
        Write-Host 'VERDICT: clear immediately -- nothing survives the kill.' -ForegroundColor Green
    } else {
        Write-Host ("VERDICT: cleared {0:n0} ms after the spawned pid exited -- a race window of that size." -f $clearedAt) -ForegroundColor Yellow
    }
} catch {
    Write-Host "Diagnostic FAILED: $_" -ForegroundColor Red
    foreach ($name in 'stdout.log', 'stderr.log') {
        $path = Join-Path $workDir $name
        if (Test-Path -LiteralPath $path) {
            Write-Host "--- $name ---"
            Get-Content -LiteralPath $path -Tail 100
        }
    }
} finally {
    if ($null -ne $process -and -not $process.HasExited) {
        $process.Kill()
        $process.WaitForExit(10000) | Out-Null
    }
    if ($IsWindows) {
        foreach ($leftover in $descendantPids) {
            Stop-Process -Id $leftover -Force -ErrorAction SilentlyContinue
        }
    }
    Remove-Item -LiteralPath $workDir -Recurse -Force -ErrorAction SilentlyContinue
}
