"""Enforces the backend dependency direction ``api -> domain <- adapters``.

The domain core must stay free of frameworks, persistence, HTTP clients, and
the outer layers (see `AGENTS.md` "Architecture").
"""

import ast
from collections.abc import Iterator
from pathlib import Path

_SRC = Path(__file__).resolve().parents[1] / "src" / "auto_scoring"
_DOMAIN = _SRC / "domain"

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
