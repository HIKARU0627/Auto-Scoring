"""Application Default Credentials (ADC) access tokens for the Vertex AI
adapter (Issue #35).

Vertex AI is the only supported way to reach Gemini in this project: the
project's Google Cloud organization policy forbids Gemini **API keys**, so
``AUTO_SCORING_GEMINI_API_KEY``-style configuration cannot work at all and
authentication has to go through ADC
(``gcloud auth application-default login``, or a workload identity /
service account on a host that has one). That is also why the GCP project
id is never configuration this repository stores: it is read back from
whatever ADC resolved at runtime, so no real project id has to be written
into ``.env.example``, docs, or a commit (AGENTS.md "Security").

``google-auth`` ships transports for ``requests`` and ``urllib3``, neither
of which this project depends on -- ``httpx`` is already the backend's HTTP
client (``openrouter_provider.py``). :class:`_HttpxAuthRequest` is the
~15-line adapter between the two, which is the whole reason no third HTTP
library is added here (AGENTS.md "Architecture": a new dependency only when
what is already present cannot meet the requirement).

Never logs, raises, or otherwise renders the access token or the refresh
token: :class:`AdcCredentialsError` carries only the exception *type* name
of whatever google-auth raised, never its message, because a failed refresh
message can quote the token endpoint's response body.
"""

from __future__ import annotations

from typing import Any

import google.auth
import httpx
from google.auth.credentials import Credentials
from google.auth.exceptions import GoogleAuthError

#: Vertex AI's OAuth scope. ADC user credentials are minted against it at
#: refresh time; the scope is not a permission grant on its own (the
#: account still needs the Vertex AI User role on the project).
_CLOUD_PLATFORM_SCOPE = "https://www.googleapis.com/auth/cloud-platform"

_DEFAULT_REFRESH_TIMEOUT_SECONDS = 30.0


class AdcCredentialsError(Exception):
    """ADC is not configured, or its access token could not be refreshed."""


class _HttpxResponse:
    """``google.auth.transport.Response`` over an ``httpx.Response``."""

    def __init__(self, response: httpx.Response) -> None:
        self.status = response.status_code
        self.headers = response.headers
        self.data = response.content


class _HttpxAuthRequest:
    """``google.auth.transport.Request`` over an ``httpx.Client``.

    google-auth calls this to talk to Google's OAuth token endpoint during
    a credential refresh. It is deliberately not the same client the
    adapter uses for Vertex AI calls' default headers -- an
    ``Authorization`` header set on that client would be sent to the token
    endpoint too.
    """

    def __init__(self, client: httpx.Client) -> None:
        self._client = client

    def __call__(
        self,
        url: str,
        method: str = "GET",
        body: bytes | None = None,
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        **kwargs: Any,
    ) -> _HttpxResponse:
        response = self._client.request(
            method,
            url,
            content=body,
            headers=headers,
            timeout=timeout if timeout is not None else _DEFAULT_REFRESH_TIMEOUT_SECONDS,
        )
        return _HttpxResponse(response)


class AdcTokenSource:
    """Resolves ADC once, then hands out a valid bearer token per call.

    ``project_id`` is whatever ADC resolved (the ADC file's
    ``quota_project_id`` for a user credential, the service account's own
    project for a service-account credential). A caller may override it
    with ``AUTO_SCORING_VERTEX_PROJECT`` for a host whose ADC resolves
    to a different project than the one Vertex AI should be billed to; it
    is never read from a committed file.
    """

    def __init__(
        self,
        *,
        credentials: Credentials | None = None,
        project_id: str | None = None,
        client: httpx.Client | None = None,
    ) -> None:
        resolved_project = project_id
        if credentials is None:
            try:
                credentials, default_project = google.auth.default(scopes=[_CLOUD_PLATFORM_SCOPE])
            except GoogleAuthError as exc:
                # Only the exception type: google-auth's own message for a
                # failed refresh can quote the token endpoint's response
                # body (AGENTS.md "Security").
                raise AdcCredentialsError(
                    "Google Application Default Credentials are not available "
                    f"({type(exc).__name__}). Run `gcloud auth application-default login`, "
                    "or run on a host with a workload identity. Gemini API keys are not an "
                    "alternative here -- they are blocked by organization policy."
                ) from None
            if resolved_project is None:
                resolved_project = default_project
        if not resolved_project or not resolved_project.strip():
            raise AdcCredentialsError(
                "Google Application Default Credentials resolved no project id. Set "
                "AUTO_SCORING_VERTEX_PROJECT, or re-run `gcloud auth "
                "application-default set-quota-project <project>`."
            )
        self._credentials = credentials
        self._project_id = resolved_project.strip()
        self._client = client if client is not None else httpx.Client()

    @property
    def project_id(self) -> str:
        return self._project_id

    def bearer_token(self) -> str:
        """A currently-valid access token, refreshing it when needed."""
        if not self._credentials.valid:
            try:
                # google-auth's base `Credentials.refresh` is declared
                # abstract and untyped; the concrete subclasses ADC
                # returns do implement it.
                self._credentials.refresh(  # type: ignore[no-untyped-call]
                    _HttpxAuthRequest(self._client)
                )
            except (GoogleAuthError, httpx.HTTPError) as exc:
                raise AdcCredentialsError(
                    f"Refreshing the ADC access token failed ({type(exc).__name__})"
                ) from None
        token = self._credentials.token
        if not isinstance(token, str) or not token:
            raise AdcCredentialsError("ADC produced no access token after a successful refresh")
        return token
