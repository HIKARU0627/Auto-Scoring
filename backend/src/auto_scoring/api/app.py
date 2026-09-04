"""FastAPI application factory for the sidecar."""

from fastapi import FastAPI
from pydantic import BaseModel

from auto_scoring import __version__
from auto_scoring.adapters.in_memory_repository import InMemoryScoreRepository
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


def create_app() -> FastAPI:
    app = FastAPI(title="Auto-Scoring Sidecar", version=__version__)
    repository = InMemoryScoreRepository()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/score")
    def score(request: ScoreRequest) -> ScoreResponse:
        result = clamp_score(request.raw, request.maximum)
        repository.save(request.key, result)
        return ScoreResponse(
            key=request.key,
            awarded=result.awarded,
            maximum=result.maximum,
            ratio=result.ratio,
        )

    return app


app = create_app()
