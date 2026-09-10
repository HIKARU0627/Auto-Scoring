"""HTTP boundary for the API-key settings screen (Issue #96).

Thin per ``AGENTS.md`` "Architecture": every handler validates its input,
calls into `adapters.credentials`, and translates the result.

* ``GET /settings/api-keys`` -- which slots exist, whether each has a key,
  **and where that key came from**. Issue #96 requires the last part: on a
  machine that has both a ``.env.local`` and a key typed into this screen,
  "there is a key" does not tell the user which one is being used.
* ``PUT /settings/api-keys/{slot_id}`` -- store a key.
* ``DELETE /settings/api-keys/{slot_id}`` -- remove it.
* ``POST /settings/api-keys/{slot_id}/verify`` -- try the key in force
  against the provider, once.

**No response here ever carries a key.** Not the one just saved, not the one
already stored, not a prefix or a masked form of either. The screen shows
*that* a key is held and where it came from, and offers to replace it; it
cannot read one back. A value the app will not display is a value that
cannot leak through a screenshot, a bug report, or a support conversation --
and there is nothing the user can do with a key they already own that
re-reading it in this app would help with.

A saved key is registered with `api.secret_redaction.SecretRegistry` in the
same breath as it is stored, so the log filter installed at startup scrubs it
from that moment on. That ordering is the point: the very next request may be
the verify call, and its failures are logged.
"""

from __future__ import annotations

from collections.abc import Callable

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from auto_scoring.adapters.credentials.api_keys import (
    MAX_API_KEY_LENGTH,
    ApiKeySettings,
    ApiKeySlot,
    ApiKeyStatus,
    ConfigurationSource,
    InvalidApiKeyError,
)
from auto_scoring.adapters.credentials.store import CredentialStoreUnavailableError
from auto_scoring.adapters.credentials.verification import (
    NOT_CONFIGURED,
    VerificationOutcome,
    verify_api_key,
)
from auto_scoring.api.secret_redaction import SecretRegistry

#: How the settings endpoints reach the provider. Injected so a test never
#: makes a live call -- the rule ``AGENTS.md`` states for every boundary, and
#: here also a rule about somebody's invoice.
CredentialVerifier = Callable[[ApiKeySlot, str], VerificationOutcome]


class ApiKeyStatusModel(BaseModel):
    """One provider's key, described without disclosing it."""

    id: str
    label: str
    configured: bool
    #: ``credential_store`` / ``environment`` / ``none``. Named
    #: ``key_source`` rather than ``source`` because the Dart generator
    #: turns the latter into ``source_``.
    key_source: ConfigurationSource
    #: The environment variable this key is read from, and the name it is
    #: filed under in the OS credential store. Shown so a developer can tell
    #: which variable the screen is talking about.
    key_variable: str
    model: str
    model_source: ConfigurationSource
    console_url: str


class ApiKeySettingsResponse(BaseModel):
    """The whole screen's state, so one round trip refreshes all of it."""

    #: ``None`` when the OS credential store works here; otherwise why it
    #: does not, in words the user can act on. A host without one still runs
    #: -- it simply cannot save a key, and reads the environment as before.
    store_unavailable_reason: str | None = None
    #: The provider priority list actually in force, and where it came from.
    #: Issue #96 keeps the development machines' Vertex-first order, so the
    #: order differs between a developer's machine and an installed copy;
    #: the screen says which one it is looking at instead of implying there
    #: is only one.
    transport_order: str
    transport_source: ConfigurationSource
    #: Whether a key has been saved or removed since the sidecar started.
    #: The provider chain is built once at startup, so while this is true
    #: what is stored and what is running disagree -- and the screen offers
    #: to restart the sidecar rather than leaving the user to discover it at
    #: the next grading job.
    restart_required: bool
    keys: list[ApiKeyStatusModel]


class SaveApiKeyRequest(BaseModel):
    value: str = Field(min_length=1, max_length=MAX_API_KEY_LENGTH)


class VerifyApiKeyResponse(BaseModel):
    """The outcome of one live call. Fixed sentences and a status number."""

    result: str
    detail: str
    status_code: int | None = None
    #: Which key was tried -- the stored one or the environment's. Without
    #: it, "it works" on a machine with both is an ambiguous answer.
    key_source: ConfigurationSource


def _status_model(status_: ApiKeyStatus) -> ApiKeyStatusModel:
    return ApiKeyStatusModel(
        id=status_.slot.id,
        label=status_.slot.label,
        configured=status_.configured,
        key_source=status_.source,
        key_variable=status_.slot.key_variable,
        model=status_.model,
        model_source=status_.model_source,
        console_url=status_.slot.console_url,
    )


def build_settings_router(
    settings: ApiKeySettings,
    *,
    secret_registry: SecretRegistry,
    verifier: CredentialVerifier | None = None,
) -> APIRouter:
    """Routes over ``settings``.

    ``settings`` is the same object the composition root built the provider
    chain from, so `ApiKeySettingsResponse.restart_required` reflects this
    process's own history rather than a guess made by comparing values.
    """
    call_provider = verifier or verify_api_key
    router = APIRouter(tags=["settings"])

    def _snapshot() -> ApiKeySettingsResponse:
        order, order_source = settings.transport_order()
        return ApiKeySettingsResponse(
            store_unavailable_reason=settings.store_unavailable_reason,
            transport_order=order,
            transport_source=order_source,
            restart_required=settings.changed_since_start,
            keys=[_status_model(item) for item in settings.statuses()],
        )

    def _slot_or_404(slot_id: str) -> ApiKeySlot:
        slot = settings.slot(slot_id)
        if slot is None:
            # The id, not the label: it came from the caller, and the set of
            # valid ids is public (`GET /settings/api-keys` lists them).
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown API key slot")
        return slot

    @router.get("/settings/api-keys", response_model=ApiKeySettingsResponse)
    def read_api_keys() -> ApiKeySettingsResponse:
        return _snapshot()

    @router.put("/settings/api-keys/{slot_id}", response_model=ApiKeySettingsResponse)
    def save_api_key(slot_id: str, request: SaveApiKeyRequest) -> ApiKeySettingsResponse:
        slot = _slot_or_404(slot_id)
        try:
            stored = settings.save(slot, request.value)
        except InvalidApiKeyError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from None
        except CredentialStoreUnavailableError as error:
            # 503, not 500: nothing is broken in this app: this host has no
            # place to keep a secret. The message says so and the screen
            # keeps the environment-variable route visible.
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from None
        secret_registry.add(stored)
        return _snapshot()

    @router.delete("/settings/api-keys/{slot_id}", response_model=ApiKeySettingsResponse)
    def delete_api_key(slot_id: str) -> ApiKeySettingsResponse:
        slot = _slot_or_404(slot_id)
        try:
            settings.delete(slot)
        except CredentialStoreUnavailableError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from None
        return _snapshot()

    @router.post("/settings/api-keys/{slot_id}/verify", response_model=VerifyApiKeyResponse)
    def verify(slot_id: str) -> VerifyApiKeyResponse:
        slot = _slot_or_404(slot_id)
        resolved = settings.key(slot)
        if resolved is None:
            return _verification_model(NOT_CONFIGURED, ConfigurationSource.NONE)
        value, source = resolved
        # Registered before the call, not after: this is the first thing to
        # send the key anywhere, and it is the call whose failures get
        # logged. A key that arrived through the environment is already
        # covered by `configuration_secrets`; adding it again is free.
        secret_registry.add(value)
        return _verification_model(call_provider(slot, value), source)

    return router


def _verification_model(
    outcome: VerificationOutcome, source: ConfigurationSource
) -> VerifyApiKeyResponse:
    return VerifyApiKeyResponse(
        result=outcome.result.value,
        detail=outcome.detail,
        status_code=outcome.status_code,
        key_source=source,
    )
