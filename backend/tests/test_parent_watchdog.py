"""Tests for the sidecar's parent watchdog (Issue #211).

Two halves, on purpose:

* The **decision** -- is the parent gone, and how often may we ask -- is pure
  (`parent_is_gone`, `poll_interval_seconds`, `_watch`) and is tested with
  values and doubles. Pid reuse lives here: it cannot be provoked on demand,
  but it is only ever *judged* in one function, so judging it is what gets
  tested.
* The **guarantee** -- a real sidecar-shaped process really outlives nothing
  -- is tested with real processes and a real ``SIGKILL``. Anything less
  would prove the code runs, not that the deadline holds.

No test here waits out a fixed duration for something to happen: `_wait_until`
returns the instant its predicate is true, and every assertion about elapsed
time is a bound the observed event has to fit inside. The one place a test
does spend real time is `test_a_child_without_a_parent_pid_outlives_its_parent`,
which asserts something *never* happens; its window starts only once a sibling
child with the same wiring has already died, so the window cannot end before
the effect it is looking for would have shown up.
"""

from __future__ import annotations

import contextlib
import json
import os
import socket
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from pathlib import Path

import pytest

from auto_scoring.adapters.data_root_lock import DataRootLockedError, acquire_data_root_lock
from auto_scoring.adapters.parent_watchdog import (
    DETECTION_BUDGET_SECONDS,
    ParentIdentity,
    _watch,
    parent_is_gone,
    poll_interval_seconds,
    read_parent_identity,
    start_parent_watchdog,
)

_ALIVE = ParentIdentity(pid=4242, start_token="8899")


# --------------------------------------------------------------------------
# The decision: is the parent gone?
# --------------------------------------------------------------------------


def test_the_same_process_under_the_same_pid_is_still_alive() -> None:
    assert parent_is_gone(_ALIVE, ParentIdentity(pid=4242, start_token="8899")) is False


def test_no_process_under_that_pid_is_gone() -> None:
    assert parent_is_gone(_ALIVE, None) is True


def test_a_reused_pid_is_not_mistaken_for_the_parent() -> None:
    """Issue #211 requirement 3.

    The pid is unchanged and something is running under it -- everything a
    bare ``os.kill(pid, 0)`` can see -- and yet the parent is gone: the OS
    handed its number to an unrelated process. The start token is the whole
    difference, so this is the one assertion that fails if anyone ever
    simplifies the comparison down to the number.
    """
    reused = ParentIdentity(pid=4242, start_token="99715")

    assert parent_is_gone(_ALIVE, reused) is True


def test_an_unreadable_identity_counts_as_alive() -> None:
    """The asymmetry `parent_is_gone` documents: killing a working sidecar
    mid-grade costs the user their run, while keeping an orphan alive costs
    them the data-root lock's "already running" screen, which is the very
    thing that stops it from mattering.
    """
    unknown = ParentIdentity(pid=4242, start_token=None)

    assert parent_is_gone(_ALIVE, unknown) is False
    assert parent_is_gone(unknown, _ALIVE) is False


# --------------------------------------------------------------------------
# The decision: how often may we ask?
# --------------------------------------------------------------------------


def test_several_probes_fit_inside_the_detection_budget() -> None:
    """The deadline has to survive one slow or failed probe, so the interval
    is a fraction of the budget rather than the budget itself.
    """
    interval = poll_interval_seconds(DETECTION_BUDGET_SECONDS)

    assert 0 < interval <= DETECTION_BUDGET_SECONDS / 2


def test_the_default_interval_is_the_one_the_budget_asks_for() -> None:
    assert poll_interval_seconds() == poll_interval_seconds(DETECTION_BUDGET_SECONDS)


def test_a_budget_that_is_not_a_duration_is_refused() -> None:
    with pytest.raises(ValueError, match="positive"):
        poll_interval_seconds(0)


# --------------------------------------------------------------------------
# The loop, with the clock and the exit replaced
# --------------------------------------------------------------------------


def test_the_loop_waits_the_computed_interval_and_exits_once_the_parent_goes() -> None:
    observations: list[ParentIdentity | None] = [_ALIVE, _ALIVE, None]
    slept: list[float] = []
    exits = 0

    def _terminate() -> None:
        nonlocal exits
        exits += 1

    def _sleep(seconds: float) -> None:
        # Bounded, so a loop that stops looking at the probe *fails* here
        # instead of spinning. Found by mutation: replacing the condition
        # with `while True` hung this test rather than reddening it, and a
        # test that hangs reports nothing.
        assert len(slept) < len(observations) + 1, "the loop never re-read the parent's identity"
        slept.append(seconds)

    _watch(
        _ALIVE.pid,
        _ALIVE,
        0.25,
        lambda _pid: observations.pop(0),
        _terminate,
        _sleep,
    )

    assert observations == []
    assert slept == [0.25, 0.25]
    assert exits == 1


def test_the_loop_exits_when_the_parent_was_already_gone_at_startup() -> None:
    """No baseline to compare against is not a reason to keep running: a
    supervisor that died between spawning this process and this thread
    starting is exactly the orphan the watchdog exists for.
    """
    exits = 0

    def _terminate() -> None:
        nonlocal exits
        exits += 1

    _watch(
        _ALIVE.pid,
        None,
        0.25,
        lambda _pid: pytest.fail("a probe should not be needed"),
        _terminate,
        lambda _seconds: pytest.fail("a sleep should not be needed"),
    )

    assert exits == 1


def test_the_watchdog_runs_off_the_calling_thread() -> None:
    """Issue #211 requirement 1: the deadline holds while the main thread is
    blocked inside a minutes-long call to an AI provider. Here the calling
    thread never yields to the watchdog at all -- it only waits for it.
    """
    fired = threading.Event()
    thread = start_parent_watchdog(
        os.getpid(),
        probe=lambda _pid: None,
        terminate=fired.set,
        sleep=lambda _seconds: None,
    )

    assert fired.wait(timeout=DETECTION_BUDGET_SECONDS)
    assert thread.daemon


def test_this_process_can_read_its_own_identity() -> None:
    """The Linux probe, against the one pid every test knows is alive."""
    identity = read_parent_identity(os.getpid())

    assert identity is not None
    assert identity.pid == os.getpid()
    assert identity.start_token is not None
    # Stable across reads: it identifies the process, not the moment.
    assert read_parent_identity(os.getpid()) == identity


def test_an_unused_pid_reads_back_as_no_process() -> None:
    unused = _an_unused_pid()

    assert read_parent_identity(unused) is None


def _an_unused_pid() -> int:
    """A pid nothing holds: spawn a process, wait for it, reap it.

    Racy in principle -- the OS may hand the number out again -- but not in
    the microseconds between the ``wait`` and the read, and the alternative
    (a hard-coded large number) is the one that really does collide.
    """
    finished = subprocess.Popen([sys.executable, "-c", ""])
    finished.wait()
    return finished.pid


# --------------------------------------------------------------------------
# The guarantee, with real processes and a real SIGKILL
# --------------------------------------------------------------------------

_POLL_SECONDS = 0.02

_CHILD_SOURCE = """
import json, os, socket, sys
from pathlib import Path

from auto_scoring.adapters.data_root_lock import acquire_data_root_lock
from auto_scoring.adapters.parent_watchdog import start_parent_watchdog

spec = json.loads(sys.argv[1])
data_root = Path(spec["data_root"])

# Held for as long as this process lives, exactly as the sidecar holds it.
# Its release is what the test watches for: the kernel drops it when the
# process exits, whatever the process was doing at the time.
lock = acquire_data_root_lock(data_root)

if spec["budget_seconds"] is not None:
    start_parent_watchdog(spec["parent_pid"], budget_seconds=spec["budget_seconds"])

(data_root / "ready").write_text(str(os.getpid()), encoding="utf-8")

# Stands in for the minutes-long HTTP call to an AI provider that Issue #211
# requirement 1 names: the main thread is parked inside a blocking read on a
# socket the other end never writes to, and runs no Python at all until the
# process ends. A flag some later line was meant to notice would never be
# noticed here.
blocked = socket.create_connection(("127.0.0.1", spec["never_answers_port"]))
try:
    blocked.recv(1)
except OSError:
    # The test closed the far end, which is how a surviving child is asked
    # to go home. Not a failure, and a traceback for it is CI noise.
    pass
"""

_PARENT_SOURCE = """
import json, os, socket, subprocess, sys

child_script, specs_json, never_answers_port = sys.argv[1], sys.argv[2], int(sys.argv[3])

for spec in json.loads(specs_json):
    spec["parent_pid"] = os.getpid()
    spec["never_answers_port"] = never_answers_port
    subprocess.Popen([sys.executable, child_script, json.dumps(spec)])

# Parked the same way its children are, so this process only ever ends by
# being killed -- and, if the test itself dies first, by the socket closing.
blocked = socket.create_connection(("127.0.0.1", never_answers_port))
try:
    blocked.recv(1)
except OSError:
    pass
"""


@pytest.fixture
def never_answers_port() -> Iterator[int]:
    """A listening socket that accepts connections and never writes to them.

    Nothing calls ``accept``; the kernel completes the handshake into the
    backlog by itself, which is all a blocked ``recv`` needs. Closing it at
    the end of the test unblocks every process still parked on it, so a
    failed assertion cannot leave one behind.
    """
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(8)
    try:
        yield int(listener.getsockname()[1])
    finally:
        listener.close()


@contextlib.contextmanager
def _family(
    tmp_path: Path,
    port: int,
    budgets: dict[str, float | None],
) -> Iterator[subprocess.Popen[bytes]]:
    """Start one parent holding one child per entry in ``budgets``.

    A ``None`` budget is a child started the way pytest and a developer start
    the sidecar: no ``--parent-pid``, so no watchdog at all.
    """
    child_script = tmp_path / "child.py"
    child_script.write_text(_CHILD_SOURCE, encoding="utf-8")
    parent_script = tmp_path / "parent.py"
    parent_script.write_text(_PARENT_SOURCE, encoding="utf-8")

    specs = [
        {"data_root": str(tmp_path / name), "budget_seconds": budget}
        for name, budget in budgets.items()
    ]
    parent = subprocess.Popen(
        [
            sys.executable,
            str(parent_script),
            str(child_script),
            json.dumps(specs),
            str(port),
        ]
    )
    try:
        for name in budgets:
            _wait_until(
                (tmp_path / name / "ready").is_file,
                timeout=60,
                description=f"child {name!r} never reported itself ready",
            )
        yield parent
    finally:
        parent.kill()
        parent.wait()
        for name in budgets:
            _kill_if_running(tmp_path / name)


def _kill_if_running(data_root: Path) -> None:
    """Best effort: the process named in ``ready`` has usually already gone.

    ``OSError``, not just ``ProcessLookupError``: on Windows `os.kill` is
    ``TerminateProcess`` (the hazard `adapters.parent_watchdog` documents),
    and an id no process holds comes back as a plain ``OSError`` --
    ``[WinError 87] The parameter is incorrect`` -- rather than the POSIX
    exception. Caught in CI on Windows, where the child this is cleaning up
    had already exited on its own, exactly as intended.
    """
    ready = data_root / "ready"
    if not ready.is_file():
        return
    with contextlib.suppress(OSError, ValueError):
        os.kill(int(ready.read_text(encoding="utf-8")), 9)


def _lock_is_free(data_root: Path) -> bool:
    """Whether the process that held ``data_root`` has gone.

    The lock, rather than the pid, because it answers the question without a
    race: the kernel releases it as the process exits, while a pid stays
    readable until whatever is left of the process is reaped -- and the
    reaper here is init, which the test does not control.
    """
    try:
        handle = acquire_data_root_lock(data_root)
    except DataRootLockedError:
        return False
    handle.close()
    return True


def _wait_until(predicate: Callable[[], bool], *, timeout: float, description: str) -> float:
    """Block until ``predicate`` holds; return how long that took.

    Returns the instant it becomes true, so the elapsed time it hands back is
    a measurement rather than the timeout.
    """
    started = time.monotonic()
    deadline = started + timeout
    while not predicate():
        if time.monotonic() >= deadline:
            raise AssertionError(f"{description} (waited {timeout}s)")
        time.sleep(_POLL_SECONDS)
    return time.monotonic() - started


def test_a_watched_child_dies_within_the_budget_when_its_parent_is_killed(
    tmp_path: Path,
    never_answers_port: int,
) -> None:
    """Issue #211's acceptance criterion, at the production budget.

    ``SIGKILL`` on the parent: no exit handler runs, no shutdown message is
    sent, nothing on the parent's side gets a say -- the same shape as End
    Task, ``taskkill /F`` and a crash, which is what the Windows Job Object
    this replaces was there for.
    """
    budgets: dict[str, float | None] = {"watched": DETECTION_BUDGET_SECONDS}
    with _family(tmp_path, never_answers_port, budgets) as parent:
        assert not _lock_is_free(tmp_path / "watched")

        parent.kill()
        parent.wait()

        elapsed = _wait_until(
            lambda: _lock_is_free(tmp_path / "watched"),
            timeout=DETECTION_BUDGET_SECONDS * 4,
            description="the watched child outlived its killed parent",
        )
        assert elapsed < DETECTION_BUDGET_SECONDS


def test_a_child_without_a_parent_pid_outlives_its_parent(
    tmp_path: Path,
    never_answers_port: int,
) -> None:
    """Issue #211 requirement 2: the watchdog is off unless it is asked for.

    Without this, pytest and every hand-started sidecar would be watching
    whatever spawned them, and would kill themselves the moment it went away.

    The ``watched`` sibling is here as the clock. It shares the parent, the
    kill and the wiring, so once *it* has died the window in which a watchdog
    fires is demonstrably over -- and the assertion below is then about a
    child that has no watchdog, not about one whose watchdog has not got
    round to it yet.
    """
    quick = 0.5
    budgets: dict[str, float | None] = {"watched": quick, "unwatched": None}
    with _family(tmp_path, never_answers_port, budgets) as parent:
        parent.kill()
        parent.wait()
        _wait_until(
            lambda: _lock_is_free(tmp_path / "watched"),
            timeout=DETECTION_BUDGET_SECONDS * 4,
            description="the watched sibling outlived its killed parent",
        )

        grace_ends = time.monotonic() + quick * 4
        while time.monotonic() < grace_ends:
            assert not _lock_is_free(tmp_path / "unwatched"), (
                "a sidecar started without --parent-pid must not follow its parent"
            )
            time.sleep(_POLL_SECONDS)
