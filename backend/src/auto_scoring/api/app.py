"""FastAPI application factory for the sidecar."""

from fastapi import APIRouter, Depends, FastAPI
from pydantic import BaseModel

from auto_scoring import __version__
from auto_scoring.adapters.in_memory_repository import InMemoryScoreRepository
from auto_scoring.api.auth import generate_token, require_token
from auto_scoring.domain.scoring import clamp_score


class ScoreRequest(BaseModel):
    key: str
    raw: int
    maximum: int


class ScoreResponse(BaseModel):
    key: str
    awarded: int
    maximum: int
    ratio: float


def create_app(*, api_token: str | None = None) -> FastAPI:
    """Build the sidecar app.

    ``api_token`` is the bearer token every non-health route requires. When it
    is omitted a random one is minted, so an app object always has a token and
    the protected routes are never accidentally open.
    """
    app = FastAPI(title="Auto-Scoring Sidecar", version=__version__)
    app.state.api_token = api_token or generate_token()
    repository = InMemoryScoreRepository()
    protected = APIRouter(dependencies=[Depends(require_token)])

    @app.get("/healthz")
    def healthz() -> dict[str, str]:
        return {"status": "ok"}

    @protected.post("/score")
    def score(request: ScoreRequest) -> ScoreResponse:
        result = clamp_score(request.raw, request.maximum)
        repository.save(request.key, result)
        return ScoreResponse(
            key=request.key,
            awarded=result.awarded,
            maximum=result.maximum,
            ratio=result.ratio,
        )

    app.include_router(protected)
    return app


app = create_app()
