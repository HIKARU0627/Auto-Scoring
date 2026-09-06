"""Exclusive process-level lock on an app-data root (Issue #18 review round 9, P1).

Two sidecar processes launched against the same ``--app-data-dir`` (the
runner is free to do this -- ``auto_scoring.api.sidecar``'s ``--app-data-dir``
defaults to ``cwd()/app-data`` with nothing stopping a second launch from
reusing it) would otherwise both open the same SQLite database and both run
``auto_scoring.jobs.queue.JobQueueService.start``'s own crash-recovery sweep.
That sweep cannot tell "this RUNNING row was abandoned by a process that
died" apart from "this RUNNING row is owned by a *different, still-alive*
sidecar process" -- either way it just sees a RUNNING row. Recovering the
second case reissues a job a live process is still actually processing, and
that process's own eventual finalize then loses its compare-and-set,
silently discarding real, completed work.

`acquire_data_root_lock` takes an OS-level, advisory, exclusive lock on a
file inside the data root (POSIX: ``fcntl.flock``; Windows:
``msvcrt.locking``), held for as long as the returned file object stays
open. Unlike a lock file's mere *existence*, this lock is owned by the OS
kernel, not by any content written to the file, so it cannot outlive the
process that acquired it -- the OS releases it the instant that process's
file descriptor closes, which is guaranteed on process exit even after a
crash. No stale-lock cleanup is ever needed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import IO

_LOCK_FILENAME = ".lock"


class DataRootLockedError(Exception):
    """Another process already holds the exclusive lock on this data root."""

    def __init__(self, data_root: Path) -> None:
        super().__init__(
            f"{data_root!s} is already in use by another running instance -- "
            "only one process may own a given app-data directory at a time "
            "(wait for the other instance to exit, or use a different "
            "--app-data-dir)"
        )
        self.data_root = data_root


def acquire_data_root_lock(data_root: Path) -> IO[bytes]:
    """Acquire an exclusive, OS-level lock on ``data_root``, held for as
    long as the returned file object stays open (the caller is responsible
    for closing it -- typically at the same point it stops using the
    database under ``data_root``). Raises `DataRootLockedError` if another
    live process already holds it.

    The lock file itself (``data_root/.lock``) is created if missing, but
    its *content* is never read or otherwise meaningful -- only the OS-level
    lock on the open file descriptor matters.
    """
    data_root.mkdir(parents=True, exist_ok=True)
    lock_path = data_root / _LOCK_FILENAME
    handle = open(lock_path, "a+b")  # noqa: SIM115 -- kept open for the lock's whole lifetime
    try:
        # Ensure the file has at least one byte for msvcrt.locking to lock,
        # without ever *reading* byte 0 -- that would conflict with a lock
        # another process already holds there, raising a plain
        # PermissionError before this function ever gets a chance to turn
        # it into the intended DataRootLockedError. Checking the size via
        # seek/tell touches only the position pointer, never the file's
        # actual (possibly locked) content.
        handle.seek(0, 2)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if sys.platform == "win32":
            import msvcrt

            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            except OSError as error:
                raise DataRootLockedError(data_root) from error
        else:
            import fcntl

            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            except OSError as error:
                raise DataRootLockedError(data_root) from error
    except DataRootLockedError:
        handle.close()
        raise
    return handle
