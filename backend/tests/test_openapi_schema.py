"""The committed OpenAPI schema must match what the app produces."""

import json

from auto_scoring.api.openapi_schema import SCHEMA_PATH, schema


def test_committed_schema_is_up_to_date() -> None:
    assert b"\r\n" not in SCHEMA_PATH.read_bytes()
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert committed == schema(), "run `pnpm run openapi:export` and commit the result"


def test_cancel_job_endpoint_declares_its_202_response() -> None:
    """Issue #18 review round 7, P2: POST /jobs/{job_id}/cancel answers 202
    at runtime for a RUNNING job (auto_scoring.api.jobs_router.cancel_job),
    not just the default 200 -- the schema must declare that response
    explicitly, or a contract-generated client/validator has no way to
    model the accepted-but-pending outcome and would treat the real
    response as undocumented.
    """
    responses = schema()["paths"]["/jobs/{job_id}/cancel"]["post"]["responses"]
    assert "202" in responses
    ref_200 = responses["200"]["content"]["application/json"]["schema"]["$ref"]
    ref_202 = responses["202"]["content"]["application/json"]["schema"]["$ref"]
    assert ref_202 == ref_200  # same JobResponse body shape as the 200 case


def test_healthz_is_public_and_every_other_operation_requires_bearer() -> None:
    paths = schema()["paths"]
    assert "security" not in paths["/healthz"]["get"]
    for path, path_item in paths.items():
        if path == "/healthz":
            continue
        for operation in path_item.values():
            assert operation["security"] == [{"HTTPBearer": []}]
