"""`scripts/seed-demo-app-data.py` must never delete data it did not write.

That script seeds an ``app-data/`` root for screenshots (Issue #71), and it
**resets** the root first by deleting every test in it -- which cascades to
every answer, grade, annotation and review underneath. Its guard is therefore
the only thing standing between a development convenience and grading data that
cannot be re-acquired, so it is pinned here rather than left to the script's own
docstring.

The first version of the guard checked test ids only. A demo test that someone
had taken a real answer into still has a `demo-` id, so the check passed and the
answer went with the cascade (Issue #71 review round 1, P1). The regression test
below is that exact case.

The script lives outside `backend/` (it is repository tooling, not part of the
sidecar), so it is loaded by path. It imports the sidecar package, which is why
its test belongs to this suite.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import datetime
from pathlib import Path
from types import ModuleType

import pytest

from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url

# Module-qualified: importing `Test` by name would have pytest try to collect
# the domain entity as a test class.
from auto_scoring.domain import models

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed-demo-app-data.py"

#: An id shaped the way the sidecar's own intake writes them -- no `demo-`
#: prefix. Stands in for a real answer taken into a seeded test.
REAL_SUBMISSION_ID = "5f1c0b7a-3e2d-4a11-9c8e-6d0b2f4a7c31"


@pytest.fixture(scope="module")
def seeder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("seed_demo_app_data", _SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # Registered before execution so the module can be found by name if
    # anything it imports looks for it.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _unit_of_work(root: Path) -> SqlAlchemyUnitOfWork:
    engine = create_sqlite_engine(sqlite_url(root / "database.sqlite"))
    return SqlAlchemyUnitOfWork(build_session_factory(engine))


def _submission_ids(root: Path) -> set[str]:
    with _unit_of_work(root) as uow:
        return {
            submission.id
            for test in uow.tests.list_all()
            for submission in uow.submissions.list_for_test(test.id)
        }


def _add_real_answer(root: Path, *, test_id: str) -> None:
    """Take an answer into a seeded test the way normal intake would."""
    with _unit_of_work(root) as uow:
        uow.submissions.add(
            models.Submission(
                id=REAL_SUBMISSION_ID,
                test_id=test_id,
                source_pdf_path=f"submissions/{REAL_SUBMISSION_ID}/source.pdf",
                source_pdf_sha256="9" * 64,
                page_count=1,
                created_at=datetime(2026, 9, 2, 10, 0),
            )
        )
        uow.commit()


def test_seeding_the_same_root_twice_leaves_the_same_data(
    seeder: ModuleType, tmp_path: Path
) -> None:
    root = tmp_path / "app-data"

    assert seeder.main(["--app-data-dir", str(root)]) == 0
    after_first = _submission_ids(root)
    assert seeder.main(["--app-data-dir", str(root)]) == 0

    assert _submission_ids(root) == after_first
    assert after_first, "the seeder wrote no answers at all"


def test_refuses_a_root_holding_an_answer_it_did_not_write(
    seeder: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """The P1: a real answer under a demo test must survive a re-run.

    Every id involved except the answer's own starts with `demo-`, so a guard
    that only looks at tests sees nothing wrong and lets the cascade run.
    """
    root = tmp_path / "app-data"
    assert seeder.main(["--app-data-dir", str(root)]) == 0
    seeded = _submission_ids(root)
    demo_test_id = next(test.id for test in _tests(root) if test.status is models.TestStatus.READY)
    _add_real_answer(root, test_id=demo_test_id)

    assert seeder.main(["--app-data-dir", str(root)]) != 0

    surviving = _submission_ids(root)
    assert REAL_SUBMISSION_ID in surviving, "the seeder deleted an answer it did not write"
    assert surviving == seeded | {REAL_SUBMISSION_ID}, "the seeder reset the root anyway"
    # The refusal has to say what it found, without printing ids from a root
    # that may hold real data.
    message = capsys.readouterr().err
    assert "submissions: 1" in message
    assert REAL_SUBMISSION_ID not in message


def _tests(root: Path) -> list[models.Test]:
    with _unit_of_work(root) as uow:
        return list(uow.tests.list_all())
