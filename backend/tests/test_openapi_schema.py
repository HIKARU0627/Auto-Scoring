"""The committed OpenAPI schema must match what the app produces."""

import json

from auto_scoring.api.openapi_schema import SCHEMA_PATH, schema


def test_committed_schema_is_up_to_date() -> None:
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert committed == schema(), "run `pnpm run openapi:export` and commit the result"


def test_healthz_is_public_and_score_requires_bearer() -> None:
    paths = schema()["paths"]
    assert "security" not in paths["/healthz"]["get"]
    assert paths["/score"]["post"]["security"] == [{"HTTPBearer": []}]
