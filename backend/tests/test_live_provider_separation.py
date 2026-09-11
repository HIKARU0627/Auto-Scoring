"""The default pytest run must never collect a paid live-provider probe.

Issue #54's live job sends real answer crops to paid services. The remaining
cleanup test does not need a credential, but future probes will, and the
exclusion that keeps them out of the default run is a single line in
``backend/pyproject.toml`` (``addopts = "-m 'not live'"``) that a later edit
could drop without any test noticing -- after which every push would bill.
This pins the exclusion the way ``test_architecture.py`` pins the dependency
direction: by reading the configuration and the applied run, not by trusting
intent.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

_BACKEND = Path(__file__).resolve().parents[1]
_PYPROJECT = _BACKEND / "pyproject.toml"

#: The marker a live test carries, and the exclusion the default run needs.
_LIVE_MARKER = "live"
_EXCLUSION = "not live"


def _pytest_ini_options() -> dict[str, object]:
    with _PYPROJECT.open("rb") as handle:
        data = tomllib.load(handle)
    return dict(data["tool"]["pytest"]["ini_options"])


def test_default_addopts_excludes_the_live_marker() -> None:
    addopts = _pytest_ini_options().get("addopts", "")
    assert isinstance(addopts, str)
    assert _EXCLUSION in addopts, (
        f"default pytest addopts must exclude the {_LIVE_MARKER!r} marker; without "
        "it a paid live-provider probe runs on every push (Issue #54)"
    )


def test_live_marker_is_registered() -> None:
    markers = _pytest_ini_options().get("markers", [])
    assert isinstance(markers, list)
    registered = {str(marker).split(":", 1)[0].strip() for marker in markers}
    assert _LIVE_MARKER in registered, "the 'live' marker must be registered in pyproject.toml"


def test_this_default_run_excludes_the_live_marker(pytestconfig: object) -> None:
    """The effective ``-m`` of *this* run, not just the file on disk.

    Reading the config catches the usual edit; reading the applied marker
    expression also catches a run whose configuration came from somewhere
    else. When the suite is invoked without an override this is exactly the
    default exclusion.
    """
    markexpr = pytestconfig.getoption("markexpr")  # type: ignore[attr-defined]
    assert _EXCLUSION in str(markexpr).replace("'", "").replace('"', "")
