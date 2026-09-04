"""Bearer-token authentication for the sidecar API.

Lives in the ``api`` layer: it speaks FastAPI/HTTP. The token is a plain
per-session string owned by whoever starts the sidecar; this module only
compares it in constant time and turns a mismatch into ``401``.

Health checks stay unauthenticated. Every other route depends on
:func:`require_token`, which reads the expected token from
``request.app.state.api_token`` (set by :func:`auto_scoring.api.app.create_app`).
"""

from __future__ import annotations

import hmac
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

_TOKEN_NBYTES = 32
"""256 bits of entropy, rendered as URL-safe base64 by :func:`secrets.token_urlsafe`."""

bearer_scheme = HTTPBearer(
    auto_error=False,
    description="Per-session token minted when the sidecar starts.",
)


def generate_token() -> str:
    """Return a fresh, cryptographically-random bearer token."""
    return secrets.token_urlsafe(_TOKEN_NBYTES)


async def require_token(
    request: Request,
    credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer_scheme)],
) -> None:
    """Reject the request unless it carries the sidecar's bearer token."""
    expected: str = request.app.state.api_token
    presented = credentials.credentials if credentials is not None else ""
    if not hmac.compare_digest(presented, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing or invalid bearer token",
            headers={"WWW-Authenticate": "Bearer"},
        )
