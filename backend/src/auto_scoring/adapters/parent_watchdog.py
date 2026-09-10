"""Ends this process when the process that launched it does (Issue #211).

The sidecar owns an exclusive OS-level lock on its ``app-data`` root
(`adapters.data_root_lock`) for as long as it runs. That lock is what stops
two instances from writing the same database -- and it is also what makes an
*orphaned* sidecar so expensive: while one is alive the next launch is refused
with "Auto-Scoring はすでに起動しています", and this app's user is a teacher who
will not go looking in Task Manager for a process they do not know exists.
An orphan is, for them, an app that no longer starts.

Today the Flutter shell prevents orphans from outside, with a Windows Job
Object (`app/lib/core/child_process_group.dart`): the kernel terminates every
process in the job when the last handle to it closes, and the OS closes every
handle a process holds however it dies. Node.js `child_process` has no
equivalent, so the Electron shell (Issue #201) cannot carry that guarantee
across -- `docs/poc-7-sidecar-lifecycle.md` §4 measured exactly this gap.

**The decision (Issue #211) was to move the guarantee here, into the child.**
Not for accuracy -- a Job Object is stricter -- but for verifiability: a
Windows-only mechanism no CI job can exercise is how the guarantee got lost
in the first place. From inside the sidecar, "the parent died, so this process
exits" is a thing Linux CI can kill a real process and watch happen.

Three things this module is deliberate about:

* **It is off unless asked for.** Nothing here runs without an explicit parent
  pid (``--parent-pid``, `api.sidecar`). pytest and a developer's manual
  ``uv run auto-scoring-sidecar`` launch the sidecar with no supervisor at
  all; a watchdog on by default would make them shoot themselves.
* **A pid alone is not an identity.** The OS reuses pids, so "something is
  running under pid N" does not mean "the parent is running". Every probe
  returns the pid *together with* a token that changes when the pid is
  handed to a new process -- the process's start time -- and
  `parent_is_gone` compares the token, not the number. Where the OS gives no
  token the answer is "still alive": a false *positive* here kills a working
  sidecar mid-grade, while a false negative only leaves the orphan the
  data-root lock already handles.
* **The lock stays the last resort.** This watchdog is a convenience for the
  user, not a correctness mechanism. `acquire_data_root_lock` is what
  actually keeps two processes off one database, and it stays in place for
  every case this module misses (Issue #211 requirement 4).

`os.kill(pid, 0)` -- the usual POSIX liveness probe -- is **not** used as the
portable path. On Windows, Python's `os.kill` calls ``TerminateProcess`` for
any signal that is not ``CTRL_C_EVENT``/``CTRL_BREAK_EVENT``, so
``os.kill(parent_pid, 0)`` would *kill the parent* rather than ask after it.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

PARENT_EXITED_EXIT_CODE = 4
"""Exit code for "the process that launched this one is gone".

Its own number, distinct from `api.sidecar`'s ``1``/``3``, so a
``sidecar.log`` read after the fact tells a deliberate shutdown apart from a
crash. Nothing reads it live -- by definition the process that would have is
the one that died.
"""

DETECTION_BUDGET_SECONDS = 5.0
"""How long the parent may be dead before this process must be gone too.

Issue #211 requirement 1. The number is a user-experience budget, not a
technical limit: it is the pause a teacher tolerates between force-quitting
the app and being able to start it again.
"""

POLLS_PER_BUDGET = 5
"""Probes fitted inside one budget, so a missed probe is not a missed deadline."""


@dataclass(frozen=True)
class ParentIdentity:
    """A pid *and* something that tells one occupant of that pid from the next.

    ``start_token`` is opaque: the only thing anyone may do with it is compare
    it with another token read for the same pid. ``None`` means this OS gave
    us no way to tell occupants apart -- see `parent_is_gone` for what that
    costs.
    """

    pid: int
    start_token: str | None


def parent_is_gone(baseline: ParentIdentity, observed: ParentIdentity | None) -> bool:
    """Whether the process recorded as ``baseline`` has stopped running.

    Pure, and the whole of the decision: everything platform-specific is in
    reading the two identities, never in judging them. That split is what
    makes pid reuse -- the failure this cannot provoke on demand -- testable
    at all (Issue #211 requirement 3).

    ``observed is None`` means no process holds that pid: gone. A *different*
    occupant (same pid, different start token) is equally gone -- that is the
    reuse case, and the one a bare ``os.kill(pid, 0)`` gets wrong.

    An unknown token on either side answers "alive". Some OS paths cannot
    produce one (no ``/proc``, a query the OS refuses), and the cost of the
    two mistakes is not symmetric: guessing "gone" ends a sidecar in the
    middle of a teacher's grading run, while guessing "alive" leaves an
    orphan that `adapters.data_root_lock` still contains.
    """
    if observed is None:
        return True
    if baseline.start_token is None or observed.start_token is None:
        return False
    return observed.start_token != baseline.start_token


def poll_interval_seconds(budget_seconds: float = DETECTION_BUDGET_SECONDS) -> float:
    """The gap between two probes, given the deadline they have to meet.

    Pure, and separated from the loop for the same reason as `parent_is_gone`:
    a test can assert the timing property (several probes fit inside the
    budget, so the deadline survives one slow or failed probe) without
    spending the budget in real time.
    """
    if budget_seconds <= 0:
        raise ValueError(f"budget_seconds must be positive, got {budget_seconds!r}")
    return budget_seconds / POLLS_PER_BUDGET


def read_parent_identity(pid: int) -> ParentIdentity | None:
    """Read the identity of whatever process currently holds ``pid``.

    ``None`` when nothing does. See `ParentIdentity.start_token` for the
    ``ParentIdentity(pid, None)`` case: something is there, but this OS will
    not say whether it is the same something.
    """
    if sys.platform == "win32":
        return _windows_identity(pid)
    return _posix_identity(pid)


def _exit_now() -> None:
    """Leave immediately, without unwinding anything.

    `os._exit`, not `sys.exit`: a raised `SystemExit` only ends the thread
    that raises it, and even from the main thread it would wait on whatever
    the process is currently blocked in. Nothing is lost by skipping the
    unwind -- the data-root lock and the listening socket are kernel-owned and
    released by the exit itself, the database is SQLite in WAL mode, and every
    file this app writes is written through `adapters.atomic`. This is the
    same abrupt end the Job Object it replaces has always given the sidecar
    on Windows.
    """
    logging.getLogger(__name__).error(
        "the process that launched this sidecar is gone; exiting (%d)",
        PARENT_EXITED_EXIT_CODE,
    )
    # Flushes and closes every handler, so the line above reaches sidecar.log
    # -- os._exit runs no atexit hook that would otherwise do it.
    logging.shutdown()
    os._exit(PARENT_EXITED_EXIT_CODE)


def start_parent_watchdog(
    parent_pid: int,
    *,
    budget_seconds: float = DETECTION_BUDGET_SECONDS,
    probe: Callable[[int], ParentIdentity | None] = read_parent_identity,
    terminate: Callable[[], None] = _exit_now,
    sleep: Callable[[float], None] = time.sleep,
) -> threading.Thread:
    """Watch ``parent_pid`` from a daemon thread; end this process when it dies.

    A thread, and an exit taken from inside it, because the deadline has to
    hold *whatever the rest of the process is doing* (Issue #211 requirement
    1). The sidecar spends minutes at a time blocked in one HTTP call to an
    AI provider; a check folded into the event loop, or a flag some other code
    is expected to notice, would not run until that call came back.

    ``probe``/``terminate``/``sleep`` are injected so the loop can be tested
    without a real parent, a real clock, or a real exit.
    """
    baseline = probe(parent_pid)
    thread = threading.Thread(
        target=_watch,
        args=(parent_pid, baseline, poll_interval_seconds(budget_seconds), probe, terminate, sleep),
        name="parent-watchdog",
        daemon=True,
    )
    thread.start()
    return thread


def _watch(
    parent_pid: int,
    baseline: ParentIdentity | None,
    interval: float,
    probe: Callable[[int], ParentIdentity | None],
    terminate: Callable[[], None],
    sleep: Callable[[float], None],
) -> None:
    if baseline is not None:
        while not parent_is_gone(baseline, probe(parent_pid)):
            sleep(interval)
    # Reached with `baseline is None` too: a parent that was already gone when
    # this thread started is still a parent that is gone.
    terminate()


def _posix_identity(pid: int) -> ParentIdentity | None:
    """Linux: the start time out of ``/proc/<pid>/stat``. Other POSIX: existence.

    ``starttime`` (field 22) counts clock ticks since boot, so a pid handed to
    a new process gets a new value -- which is exactly the token
    `parent_is_gone` needs.
    """
    try:
        raw = (Path("/proc") / str(pid) / "stat").read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        if Path("/proc").is_dir():
            # A procfs that has no entry for this pid is procfs saying the
            # process does not exist.
            return None
        # No procfs at all (macOS): fall back to a bare existence probe, which
        # cannot see reuse. Safe on POSIX, where signal 0 really is a
        # permission check and nothing else -- unlike on Windows, where
        # `os.kill` terminates (see this module's docstring).
        return _posix_existence(pid)
    except OSError:
        return ParentIdentity(pid, None)
    return ParentIdentity(pid, _start_token(raw))


def _posix_existence(pid: int) -> ParentIdentity | None:
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return None
    except PermissionError:
        # Alive, and owned by another user. Not our parent, then -- but
        # "probably reused" is not "reused", and `parent_is_gone`'s asymmetry
        # says an uncertain answer is "alive".
        return ParentIdentity(pid, None)
    return ParentIdentity(pid, None)


def _start_token(stat_line: str) -> str | None:
    """Field 22 of a ``/proc/<pid>/stat`` line.

    Split from the last ``")"`` rather than on whitespace from the left:
    field 2 is the executable name, in parentheses, and it may itself contain
    spaces and parentheses.
    """
    _, _, after_comm = stat_line.rpartition(") ")
    fields = after_comm.split()
    # after_comm starts at field 3, so field 22 is index 19.
    return fields[19] if len(fields) > 19 else None


def _windows_identity(pid: int) -> ParentIdentity | None:
    """Windows: the process's creation time, via ``kernel32``.

    ``ctypes`` rather than a dependency: `psutil` would answer this in one
    line, but it is a compiled package added to the frozen bundle for four
    Win32 calls (`AGENTS.md` "Architecture": a dependency only when what is
    already here cannot do the job).

    Not verifiable from Linux -- mypy and pytest both skip this branch there,
    and Issue #211's acceptance is deliberately written against the Linux
    path. The parts that decide anything (`parent_is_gone`,
    `poll_interval_seconds`, `_watch`) are platform-free and covered; this
    function only reads two numbers.
    """
    if sys.platform != "win32":  # pragma: no cover -- guards the narrowing below
        raise AssertionError("_windows_identity is for win32 only")

    import ctypes
    from ctypes import wintypes

    process_query_limited_information = 0x1000
    error_invalid_parameter = 87

    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    handle = kernel32.OpenProcess(process_query_limited_information, False, pid)
    if not handle:
        # The documented answer for "there is no process with this id". Any
        # other refusal (access denied, above all) is this process failing to
        # look, not the parent being gone.
        if ctypes.get_last_error() == error_invalid_parameter:
            return None
        return ParentIdentity(pid, None)
    try:
        creation = wintypes.FILETIME()
        exited = wintypes.FILETIME()
        kernel_time = wintypes.FILETIME()
        user_time = wintypes.FILETIME()
        if not kernel32.GetProcessTimes(
            handle,
            ctypes.byref(creation),
            ctypes.byref(exited),
            ctypes.byref(kernel_time),
            ctypes.byref(user_time),
        ):
            return ParentIdentity(pid, None)
        if exited.dwHighDateTime or exited.dwLowDateTime:
            # A pid whose process has already exited stays openable for as
            # long as anything still holds a handle to it, and its creation
            # time never changes -- so the token alone would call a dead
            # parent alive forever. A non-zero exit time is the OS saying it
            # is dead.
            return None
        return ParentIdentity(pid, f"{creation.dwHighDateTime}:{creation.dwLowDateTime}")
    finally:
        kernel32.CloseHandle(handle)
