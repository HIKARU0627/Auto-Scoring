"""Enforces the backend dependency direction ``api -> domain <- adapters``.

The domain core must stay free of frameworks, persistence, HTTP clients, and
the outer layers (see `AGENTS.md` "Architecture").
"""

import ast
from collections.abc import Iterator
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "auto_scoring"
_DOMAIN = _SRC / "domain"
_DB = _SRC / "db"

_FORBIDDEN_PREFIXES = (
    "fastapi",
    "starlette",
    "sqlalchemy",
    "alembic",
    "httpx",
    "requests",
    "uvicorn",
    "auto_scoring.api",
    "auto_scoring.adapters",
    "auto_scoring.db",
)

# The db layer may use SQLAlchemy / Alembic but must not reach back up the stack.
_DB_FORBIDDEN_PREFIXES = (
    "fastapi",
    "auto_scoring.api",
    "auto_scoring.adapters",
)


def _imported_modules(path: Path) -> Iterator[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                yield alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module


def test_domain_has_no_forbidden_imports() -> None:
    offenders = [
        f"{path.relative_to(_SRC)}: imports {module}"
        for path in sorted(_DOMAIN.rglob("*.py"))
        for module in _imported_modules(path)
        if module.startswith(_FORBIDDEN_PREFIXES)
    ]
    assert not offenders, "domain layer must be framework-free:\n" + "\n".join(offenders)


def test_domain_package_exists() -> None:
    assert (_DOMAIN / "__init__.py").is_file()


def test_db_layer_does_not_import_api_or_adapters() -> None:
    offenders = [
        f"{path.relative_to(_SRC)}: imports {module}"
        for path in sorted(_DB.rglob("*.py"))
        for module in _imported_modules(path)
        if module.startswith(_DB_FORBIDDEN_PREFIXES)
    ]
    assert not offenders, "db layer must not depend on outer layers:\n" + "\n".join(offenders)


def test_questions_and_rubrics_have_no_in_place_update_path() -> None:
    """Issue #112: 設問と配点は、ガード付きの全体作り直し以外では変わらないこと。

    A submission's 「確認済み」 is the record that a person confirmed every
    question *of the set that existed then*. `ensure_questions_can_be_rebuilt`
    (Issue #103) protects that by refusing to rebuild a test's questions once
    any answer has been imported -- but it only guards the two rebuild paths
    that go through `QuestionRepository.delete_for_test`.

    An **in-place** edit would slip past it entirely: the `Question` row would
    survive, so ``reviews.question_id``'s ``ON DELETE CASCADE`` would not fire,
    and a completion recorded against 5点 would silently come to describe 3点.

    What makes that impossible today is that the repositories offer no way to
    do it. That is a property of their shape rather than of any one call site,
    so it is asserted here: the day an ``update``/``set_points``/``delete``
    method appears, this fails and whoever adds it has to say what happens to
    the completions that point at the old set.
    """
    from auto_scoring.domain import repositories

    assert set(_public_protocol_methods(repositories.QuestionRepository)) == {
        "add",
        "get",
        "list_for_test",
        "delete_for_test",
    }
    assert set(_public_protocol_methods(repositories.RubricRepository)) == {
        "add",
        "get_for_question",
    }


def _public_protocol_methods(protocol: type) -> Iterator[str]:
    """The method names a `Protocol` declares itself, ignoring the machinery
    `typing.Protocol` adds to every subclass.
    """
    for name, value in vars(protocol).items():
        if name.startswith("_"):
            continue
        if callable(value):
            yield name
