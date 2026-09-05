"""Tests for the exclusive data-root lock (Issue #18 review round 9, P1)."""

from __future__ import annotations

from pathlib import Path

import pytest

from auto_scoring.adapters.data_root_lock import DataRootLockedError, acquire_data_root_lock


def test_acquire_creates_the_lock_file_under_the_data_root(tmp_path: Path) -> None:
    handle = acquire_data_root_lock(tmp_path)
    try:
        assert (tmp_path / ".lock").exists()
    finally:
        handle.close()


def test_a_second_acquire_fails_while_the_first_handle_is_still_open(tmp_path: Path) -> None:
    first = acquire_data_root_lock(tmp_path)
    try:
        with pytest.raises(DataRootLockedError):
            acquire_data_root_lock(tmp_path)
    finally:
        first.close()


def test_acquire_succeeds_again_once_the_first_handle_is_closed(tmp_path: Path) -> None:
    """Simulates the owning process having exited (gracefully, or crashed --
    the OS releases the lock the instant the file descriptor closes either
    way, so there is no stale-lock state to detect or clean up)."""
    first = acquire_data_root_lock(tmp_path)
    first.close()

    second = acquire_data_root_lock(tmp_path)
    second.close()


def test_acquire_creates_the_data_root_if_missing(tmp_path: Path) -> None:
    missing_root = tmp_path / "not-created-yet"
    handle = acquire_data_root_lock(missing_root)
    try:
        assert missing_root.is_dir()
    finally:
        handle.close()
