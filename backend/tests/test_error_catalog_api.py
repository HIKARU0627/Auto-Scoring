"""API tests for the reviewed 誤答カタログ (Issue #209).

Drives the three endpoints against a real app, a real SQLite file and a real
`LocalFileStore`. Every fixture is synthetic (``AGENTS.md`` "Security"): the
real catalogue rows are the tutoring school's copyrighted prose and appear
nowhere here.

What is pinned: the three "no catalogue" states stay distinguishable as wire
values, a human edit survives the next import unless overwritten on purpose,
and a save against a stale revision is refused rather than silently clobbering
another reviewer's rows.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import openpyxl
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker

from auto_scoring.adapters.local_storage import LocalFileStore
from auto_scoring.adapters.unit_of_work import SqlAlchemyUnitOfWork
from auto_scoring.api.app import create_app
from auto_scoring.db.engine import build_session_factory, create_sqlite_engine, sqlite_url
from auto_scoring.domain.intake_template import MaterialRole
from auto_scoring.domain.test_material import TestMaterial
from tests.support import at, make_test

_TOKEN = "error-catalog-token"

_HEADER = ["回数", "問題番号", "生徒の誤り方・現状", "採点基準", "赤入れ案"]
_ROWS = [
    ["架空の講座名"],
    _HEADER,
    ["第1回", "問1", "架空の誤答A", "3点減", "架空の赤入れA"],
]
_UNREADABLE_ROWS = [["日付", "担当"], ["2026-09-10", "架空の氏名"]]


def _auth() -> dict[str, str]:
    return {"Authorization": f"Bearer {_TOKEN}"}


@pytest.fixture
def data_root(tmp_path: Path) -> Path:
    return tmp_path / "app-data"


@pytest.fixture
def client(data_root: Path) -> TestClient:
    return TestClient(create_app(api_token=_TOKEN, data_root=data_root))


@pytest.fixture
def store(data_root: Path) -> LocalFileStore:
    return LocalFileStore(data_root)


def _session_factory(data_root: Path) -> sessionmaker[Session]:
    return build_session_factory(create_sqlite_engine(sqlite_url(data_root / "database.sqlite")))


def _seed_test(data_root: Path, materials: list[TestMaterial]) -> None:
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        if uow.tests.get("test-1") is None:
            uow.tests.add(make_test(id="test-1"))
        for material in materials:
            uow.test_materials.add(material)
        uow.commit()


def _add_materials(data_root: Path, materials: list[TestMaterial]) -> None:
    _seed_test(data_root, materials)


def _material(stored_path: str) -> TestMaterial:
    return TestMaterial(
        id=f"material-{stored_path}",
        test_id="test-1",
        role=MaterialRole.ANNOTATION_RESOURCE,
        stored_path=stored_path,
        sha256=hashlib.sha256(stored_path.encode()).hexdigest(),
        size_bytes=1,
        original_filename=None,
        created_at=at(),
    )


def _write_xlsx(store: LocalFileStore, stored_path: str, rows: list[list[Any]]) -> None:
    path = store.resolve_stored_path(stored_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    workbook = openpyxl.Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    workbook.save(path)


def _seed_excel(data_root: Path, store: LocalFileStore, rows: list[list[Any]]) -> None:
    _write_xlsx(store, "tests/test-1/03.xlsx", rows)
    _seed_test(data_root, [_material("tests/test-1/03.xlsx")])


def _import(client: TestClient, *, policy: str = "keep_edited") -> Any:
    return client.post(
        "/tests/test-1/error-catalog/import",
        headers=_auth(),
        json={"on_conflict": policy},
    )


def test_the_three_no_catalogue_states_are_distinct_wire_values(
    client: TestClient, data_root: Path, store: LocalFileStore
) -> None:
    """Judgment 3: (a) nothing registered, (b) Word only, (c) registered but
    unreadable must not collapse into one another -- and (c) must not look
    like (a), which was the whole point of Issue #106."""
    _seed_test(data_root, [])
    not_registered = client.get("/tests/test-1/error-catalog", headers=_auth()).json()["state"]

    _write_xlsx(store, "tests/test-1/03.docx", [["not", "excel"]])
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        uow.test_materials.add(_material("tests/test-1/03.docx"))
        uow.commit()
    word_only = client.get("/tests/test-1/error-catalog", headers=_auth()).json()["state"]

    # Now add an Excel 添削資料. Reading it is never attempted before the
    # import, so the state must already say "registered but no catalogue".
    _seed_excel(data_root, store, _UNREADABLE_ROWS)
    unreadable = client.get("/tests/test-1/error-catalog", headers=_auth()).json()["state"]

    assert len({not_registered, word_only, unreadable}) == 3
    assert (not_registered, word_only, unreadable) == (
        "not_registered",
        "word_only",
        "unreadable",
    )


def test_import_makes_the_state_available_and_lists_rows(
    client: TestClient, data_root: Path, store: LocalFileStore
) -> None:
    _seed_excel(data_root, store, _ROWS)

    response = _import(client)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["state"] == "available"
    assert body["imported"] is True
    assert body["entry_count"] == 1
    (entry,) = body["entries"]
    assert entry["mistake"] == "架空の誤答A"
    assert entry["edited"] is False


def test_an_unreadable_import_is_recorded_not_returned_empty(
    client: TestClient, data_root: Path, store: LocalFileStore
) -> None:
    _seed_excel(data_root, store, _UNREADABLE_ROWS)

    response = _import(client)
    assert response.status_code == 422
    body = client.get("/tests/test-1/error-catalog", headers=_auth()).json()
    assert body["state"] == "unreadable"
    assert body["imported"] is False
    assert body["entries"] == []
    assert "no_header_row" in body["import_error"]


def test_import_refuses_a_test_without_or_with_only_word_materials(
    client: TestClient, data_root: Path, store: LocalFileStore
) -> None:
    _seed_test(data_root, [])
    assert _import(client).status_code == 409

    _write_xlsx(store, "tests/test-1/03.docx", [["x"]])
    with SqlAlchemyUnitOfWork(_session_factory(data_root)) as uow:
        uow.test_materials.add(_material("tests/test-1/03.docx"))
        uow.commit()
    assert _import(client).status_code == 409


def test_import_requires_an_explicit_conflict_policy(
    client: TestClient, data_root: Path, store: LocalFileStore
) -> None:
    """Mutation 4's guard: there is no default, so a caller can never trigger
    a silent overwrite by omitting the field."""
    _seed_excel(data_root, store, _ROWS)
    response = client.post("/tests/test-1/error-catalog/import", headers=_auth(), json={})
    assert response.status_code == 422


def test_editing_marks_rows_and_bumps_the_revision(
    client: TestClient, data_root: Path, store: LocalFileStore
) -> None:
    _seed_excel(data_root, store, _ROWS)
    assert _import(client).status_code == 200

    response = client.put(
        "/tests/test-1/error-catalog",
        headers=_auth(),
        json={
            "revision": 1,
            "entries": [{"mistake": "架空の訂正A", "red_ink": "架空の訂正赤入れ"}],
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["revision"] == 2
    (entry,) = body["entries"]
    assert entry["mistake"] == "架空の訂正A"
    assert entry["edited"] is True

    # And it is durable, not just echoed.
    reread = client.get("/tests/test-1/error-catalog", headers=_auth()).json()
    assert reread["entries"][0]["mistake"] == "架空の訂正A"


def test_a_save_against_a_stale_revision_is_rejected(
    client: TestClient, data_root: Path, store: LocalFileStore
) -> None:
    """Mutation 1's guard: removing the compare-and-set would let the second
    save below overwrite a revision the first reviewer never saw."""
    _seed_excel(data_root, store, _ROWS)
    assert _import(client).status_code == 200

    first = client.put(
        "/tests/test-1/error-catalog",
        headers=_auth(),
        json={"revision": 1, "entries": [{"mistake": "A", "red_ink": "r"}]},
    )
    assert first.status_code == 200
    assert first.json()["revision"] == 2

    stale = client.put(
        "/tests/test-1/error-catalog",
        headers=_auth(),
        json={"revision": 1, "entries": [{"mistake": "B", "red_ink": "r"}]},
    )
    assert stale.status_code == 409

    kept = client.get("/tests/test-1/error-catalog", headers=_auth()).json()
    assert kept["entries"][0]["mistake"] == "A"


def test_reimport_keeping_edits_preserves_the_human_row(
    client: TestClient, data_root: Path, store: LocalFileStore
) -> None:
    _seed_excel(data_root, store, _ROWS)
    assert _import(client).status_code == 200
    assert (
        client.put(
            "/tests/test-1/error-catalog",
            headers=_auth(),
            json={"revision": 1, "entries": [{"mistake": "人の訂正", "red_ink": "人の赤入れ"}]},
        ).status_code
        == 200
    )

    response = _import(client, policy="keep_edited")
    assert response.status_code == 200, response.text
    (entry,) = response.json()["entries"]
    assert entry["mistake"] == "人の訂正"
    assert entry["edited"] is True


def test_reimport_overwriting_replaces_the_human_row(
    client: TestClient, data_root: Path, store: LocalFileStore
) -> None:
    _seed_excel(data_root, store, _ROWS)
    assert _import(client).status_code == 200
    assert (
        client.put(
            "/tests/test-1/error-catalog",
            headers=_auth(),
            json={"revision": 1, "entries": [{"mistake": "人の訂正", "red_ink": "人の赤入れ"}]},
        ).status_code
        == 200
    )

    response = _import(client, policy="overwrite")
    assert response.status_code == 200, response.text
    (entry,) = response.json()["entries"]
    assert entry["mistake"] == "架空の誤答A"
    assert entry["edited"] is False


def test_unknown_test_is_404(client: TestClient) -> None:
    assert client.get("/tests/nope/error-catalog", headers=_auth()).status_code == 404
