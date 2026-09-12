"""HTTP boundary for the API-key settings screen (Issues #96, #386).

Thin per ``AGENTS.md`` "Architecture": every handler validates its input,
calls into `adapters.credentials`, and translates the result.

* ``GET /settings/api-keys`` -- which providers exist, whether each is usable,
  **and where each value came from**. Issue #96 requires the last part: on a
  machine that has both a ``.env.local`` and a value typed into this screen,
  "there is a value" does not tell the user which one is being used.
* ``PUT /settings/api-keys/{slot_id}`` -- store a key and/or readable
  settings (model, GCP project, region). A blank value clears that setting.
* ``DELETE /settings/api-keys/{slot_id}`` -- remove the slot's stored key.
* ``POST /settings/api-keys/{slot_id}/verify`` -- try the configuration in
  force against the provider, once.
* ``PUT /settings/transport-order`` / ``DELETE /settings/transport-order`` --
  save the use order from the screen, or remove it so the environment (and
  then the derived default) decides again (Issue #386).

**No response here ever carries a key.** Not the one just saved, not the one
already stored, not a prefix or a masked form of either. The screen shows
*that* a key is held and where it came from, and offers to replace it; it
cannot read one back. A value the app will not display is a value that
cannot leak through a screenshot, a bug report, or a support conversation --
and there is nothing the user can do with a key they already own that
re-reading it in this app would help with. Non-secret settings (model, GCP
project, region) *are* returned, because there is nothing secret about them
and a screen that hid the current model would be unusable.

A saved key is registered with `api.secret_redaction.SecretRegistry` in the
same breath as it is stored, so the log filter installed at startup scrubs it
from that moment on. That ordering is the point: the very next request may be
the verify call, and its failures are logged.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from auto_scoring.adapters.credentials.api_keys import (
    KNOWN_TRANSPORTS,
    MAX_API_KEY_LENGTH,
    ApiKeySettings,
    ApiKeySlot,
    ApiKeyStatus,
    ConfigurationSource,
    InvalidApiKeyError,
    InvalidSettingError,
    InvalidTransportOrderError,
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
CredentialVerifier = Callable[[ApiKeySlot, Mapping[str, str]], VerificationOutcome]


class TextSettingModel(BaseModel):
    """One readable (non-secret) setting: its effective value and source."""

    variable: str
    label: str
    value: str
    source: ConfigurationSource
    default_value: str
    placeholder: str
    help_text: str


class ApiKeyStatusModel(BaseModel):
    """One provider, described without disclosing its key."""

    id: str
    label: str
    #: The transport id this provider corresponds to in the use order.
    transport: str
    #: ``None`` for a provider with no key on this screen (Vertex AI/ADC,
    #: Codex app-server).
    key_variable: str | None
    #: Whether this provider can be built here at all. For a key slot that is
    #: "a key is in force"; for Vertex/Codex it is the host probe.
    configured: bool
    #: ``credential_store`` / ``environment`` / ``none``. Named
    #: ``key_source`` rather than ``source`` because the Dart generator
    #: turns the latter into ``source_``.
    key_source: ConfigurationSource
    model: str
    model_source: ConfigurationSource
    #: The environment variable the model setting is stored under, so the
    #: screen can save an edited model without inventing a name.
    model_variable: str
    #: The non-model readable settings (GCP project id, region).
    text_settings: list[TextSettingModel]
    #: `None` when this host's availability was not probed (the schema
    #: export, and any caller that injected none), so the screen says
    #: "verify to find out" rather than guessing.
    host_available: bool | None
    #: How this provider authenticates, in words, with no configuration value
    #: in it.
    auth_note: str
    #: Where to create the key. Empty for the keyless providers.
    console_url: str


class ApiKeySettingsResponse(BaseModel):
    """The whole screen's state, so one round trip refreshes all of it."""

    #: ``None`` when the OS credential store works here; otherwise why it
    #: does not, in words the user can act on. A host without one still runs
    #: -- it simply cannot save, and reads the environment as before.
    store_unavailable_reason: str | None = None
    #: The provider priority list actually in force, and where it came from.
    transport_order: str
    transport_source: ConfigurationSource
    #: Whether the order in force was saved from this screen (rather than the
    #: environment or the derived default), so the screen can offer to remove
    #: it again.
    transport_order_stored: bool
    #: The transport ids the reorder control may offer, in the project's
    #: canonical order.
    available_transports: list[str]
    #: Whether a value has been saved or removed since the sidecar started.
    #: The provider chain is built once at startup, so while this is true
    #: what is stored and what is running disagree -- and the screen offers
    #: to restart the sidecar rather than leaving the user to discover it at
    #: the next grading job.
    restart_required: bool
    keys: list[ApiKeyStatusModel]


class SaveApiKeyRequest(BaseModel):
    """Values submitted for one slot; a blank value clears that setting.

    Named for the screen it comes from rather than "slot", so the generated
    Dart/TS clients stay legible. ``value`` is kept as a key-only shorthand
    for backward compatibility with the Issue #96 clients.
    """

    value: str | None = Field(default=None, max_length=MAX_API_KEY_LENGTH)
    values: dict[str, str | None] = Field(default_factory=dict)


class SaveTransportOrderRequest(BaseModel):
    """The submitted use order, highest priority first."""

    order: list[str] = Field(min_length=1)


class VerifyApiKeyResponse(BaseModel):
    """The outcome of one live call. Fixed sentences and a status number."""

    result: str
    detail: str
    status_code: int | None = None
    #: Which value was tried -- the stored one or the environment's. Without
    #: it, "it works" on a machine with both is an ambiguous answer.
    key_source: ConfigurationSource
    #: OpenRouter account figures from ``GET /key`` (Issue #187). Separate
    #: from this app's own usage accumulation -- shown on its own line.
    provider_account_usage: float | None = None
    provider_account_limit: float | None = None


def _text_setting_models(status_: ApiKeyStatus) -> list[TextSettingModel]:
    return [
        TextSettingModel(
            variable=item.setting.variable,
            label=item.setting.label,
            value=item.value,
            source=item.source,
            default_value=item.setting.default,
            placeholder=item.setting.placeholder,
            help_text=item.setting.help_text,
        )
        for item in status_.text_settings
    ]


def _status_model(status_: ApiKeyStatus) -> ApiKeyStatusModel:
    return ApiKeyStatusModel(
        id=status_.slot.id,
        label=status_.slot.label,
        transport=status_.slot.transport,
        key_variable=status_.slot.key_variable,
        configured=status_.configured,
        key_source=status_.source,
        model=status_.model,
        model_source=status_.model_source,
        model_variable=status_.slot.model_variable,
        text_settings=_text_setting_models(status_),
        host_available=status_.host_available,
        auth_note=status_.slot.auth_note,
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
            transport_order_stored=settings.transport_order_stored(),
            available_transports=list(KNOWN_TRANSPORTS),
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
        submitted = dict(request.values)
        if request.value is not None and slot.key_variable is not None:
            submitted.setdefault(slot.key_variable, request.value)
        try:
            stored_secrets = settings.save_settings(slot, submitted)
        except (InvalidApiKeyError, InvalidSettingError) as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from None
        except CredentialStoreUnavailableError as error:
            # 503, not 500: nothing is broken in this app: this host has no
            # place to keep a secret. The message says so and the screen
            # keeps the environment-variable route visible.
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from None
        for secret in stored_secrets:
            secret_registry.add(secret)
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
        values = settings.resolved_settings(slot)
        resolved = settings.key(slot)
        if slot.key_variable is not None:
            if resolved is None:
                return _verification_model(NOT_CONFIGURED, ConfigurationSource.NONE)
            # Registered before the call, not after: this is the first thing
            # to send the key anywhere, and it is the call whose failures get
            # logged. A key that arrived through the environment is already
            # covered by `configuration_secrets`; adding it again is free.
            secret_registry.add(resolved[0])
            return _verification_model(call_provider(slot, values), resolved[1])
        # A keyless provider (Vertex AI/ADC, Codex): the "credential" is a
        # host fact, so the verify call is the host probe. There is no key to
        # register.
        return _verification_model(call_provider(slot, values), ConfigurationSource.NONE)

    @router.put("/settings/transport-order", response_model=ApiKeySettingsResponse)
    def save_transport_order(request: SaveTransportOrderRequest) -> ApiKeySettingsResponse:
        try:
            settings.save_transport_order(request.order)
        except InvalidTransportOrderError as error:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)) from None
        except CredentialStoreUnavailableError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from None
        return _snapshot()

    @router.delete("/settings/transport-order", response_model=ApiKeySettingsResponse)
    def clear_transport_order() -> ApiKeySettingsResponse:
        try:
            settings.clear_transport_order()
        except CredentialStoreUnavailableError as error:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(error)) from None
        return _snapshot()

    return router


def _verification_model(
    outcome: VerificationOutcome, source: ConfigurationSource
) -> VerifyApiKeyResponse:
    return VerifyApiKeyResponse(
        result=outcome.result.value,
        detail=outcome.detail,
        status_code=outcome.status_code,
        key_source=source,
        provider_account_usage=outcome.provider_account_usage,
        provider_account_limit=outcome.provider_account_limit,
    )
