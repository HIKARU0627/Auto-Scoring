"""The OS credential store, as this process is allowed to see it (Issue #96).

A distributed copy of this app has no ``.env.local`` and no shell to export
variables from, so the user's own API key has to be *entered on a screen* and
kept somewhere the next launch can read it back. Issue #96's decision names
that place: the operating system's credential store -- Windows Credential
Manager on the platform this ships to, whatever ``keyring`` finds elsewhere --
and rules out a settings file, ``.env``, and the database, all of which would
hold the key in plain text under the user's profile.

``keyring`` is the one dependency Issue #96 approves adding, and it is here
rather than in the domain: reading a credential is a host boundary in
``AGENTS.md``'s sense, exactly like the filesystem and the network, so the
domain never learns this module exists.

**Nothing in this module puts a stored value into a message.** Every failure
is reported as a fixed sentence plus the exception's *type* name -- the same
discipline `adapters.ai_grading._google_adc` applies to google-auth's errors,
and for the same reason: a credential backend's own exception text has been
observed to quote what it was asked to store, and these sentences are
published (they reach the settings screen and the sidecar log).

**A host with no usable backend is a supported configuration, not a broken
one.** This project's development machines are Linux, where there is no
Windows Credential Manager and often no D-Bus Secret Service either; CI has
neither. So the read path degrades to "nothing is stored here" and the app
starts exactly as it does today, reading the environment. Only the *write*
path reports a failure, because a save that silently did nothing would be the
worst outcome of the three -- the user would believe their key was kept.
"""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Final, Protocol

#: The service name every credential this app owns is filed under. One
#: constant, because it is also what a user sees in Windows Credential
#: Manager when they go looking for what this app stored.
SERVICE_NAME: Final = "Auto-Scoring"

#: Read once to find out whether there is a backend at all. A name no
#: credential is ever filed under, so the read is always a miss on a working
#: store and always an exception on a broken one.
_PROBE_ENTRY: Final = "auto-scoring-availability-probe"

_UNAVAILABLE_PREFIX: Final = "この環境では OS の資格情報ストアを利用できません"

#: How long startup may wait for the credential store to answer (Issue #429).
#:
#: The supervisor gives the whole sidecar 60 seconds to reach ``/healthz``
#: (``app/lib/core/sidecar_supervisor.dart``'s ``sidecarStartupTimeout`` and the
#: Electron supervisor's ``SIDECAR_STARTUP_TIMEOUT_MS``). A working backend
#: answers in milliseconds -- a fast local read is the point of Windows
#: Credential Manager -- so this is not a budget anything healthy approaches.
#: It exists only to stop a *stuck* backend from eating the whole 60 seconds and
#: leaving the user with ``startupTimedOut`` and no reason. 5 seconds still
#: leaves 55 for first-launch migrations, which are the sidecar's genuinely slow
#: part.
CREDENTIAL_STORE_TIMEOUT_SECONDS: Final = 5.0


class KeyringModule(Protocol):
    """The three functions this module uses from ``keyring``.

    Named as a protocol so the module can be injected (see
    :class:`KeyringCredentialStore`) without the injection point being typed
    ``Any`` -- a fake that drifts from this shape then fails type checking
    rather than at runtime on the one platform that has a real backend.
    """

    def get_password(self, service_name: str, username: str) -> str | None: ...

    def set_password(self, service_name: str, username: str, password: str) -> None: ...

    def delete_password(self, service_name: str, username: str) -> None: ...


class CredentialStoreUnavailableError(Exception):
    """A write was asked of a credential store that cannot serve it.

    Carries only a fixed sentence and an exception type name -- see the
    module docstring.
    """


class CredentialStore(Protocol):
    """Read and write named secrets belonging to this application."""

    def unavailable_reason(self) -> str | None:
        """Why this store cannot be used here, or ``None`` when it can."""

    def get(self, name: str) -> str | None:
        """The stored value, or ``None`` when there is none *or no store*."""

    def set(self, name: str, value: str) -> None:
        """Store ``value`` under ``name``.

        Raises :class:`CredentialStoreUnavailableError` when this host has no
        usable backend, rather than pretending the save happened.
        """

    def delete(self, name: str) -> None:
        """Remove ``name``. Removing what is not there is not an error."""


def _describe(exc: BaseException) -> str:
    """A publishable sentence about ``exc`` -- its type, never its message."""
    return f"{_UNAVAILABLE_PREFIX} ({type(exc).__name__})"


class KeyringCredentialStore:
    """:class:`CredentialStore` over ``keyring``.

    ``keyring_module`` is injected rather than imported here so a test can
    state which world it is in -- a Windows host with Credential Manager, a
    Linux host with no backend at all -- instead of inheriting whatever the
    machine running the test happens to have. That is the same rule
    `api.app.AIProviderFactory` follows, and it is what keeps this module's
    tests from "happening to pass" on the Linux development host (Issue #96).
    """

    def __init__(self, keyring_module: KeyringModule, *, service: str = SERVICE_NAME) -> None:
        self._keyring = keyring_module
        self._service = service
        self._reason: str | None = None
        self._probed = False

    def unavailable_reason(self) -> str | None:
        if not self._probed:
            self._probed = True
            try:
                self._read(_PROBE_ENTRY)
            except Exception as exc:  # see the module docstring: type only, never the message
                self._reason = _describe(exc)
        return self._reason

    def get(self, name: str) -> str | None:
        if self.unavailable_reason() is not None:
            return None
        try:
            stored = self._read(name)
        except Exception:  # a store that broke since the probe
            return None
        return stored or None

    def set(self, name: str, value: str) -> None:
        reason = self.unavailable_reason()
        if reason is not None:
            raise CredentialStoreUnavailableError(reason)
        try:
            self._write(name, value)
        except Exception as exc:
            # `from None`: a chained cause is rendered with its own `str()`,
            # and a backend's error text can quote what it was handed.
            raise CredentialStoreUnavailableError(_describe(exc)) from None

    def delete(self, name: str) -> None:
        if self.get(name) is None:
            # Already gone, or there is no store to remove it from. Either
            # way the caller's intent -- "this key is not kept here" -- holds,
            # and `keyring` raises rather than returning quietly for a miss.
            return
        try:
            self._remove(name)
        except Exception as exc:
            raise CredentialStoreUnavailableError(_describe(exc)) from None

    def _read(self, name: str) -> str | None:
        return self._keyring.get_password(self._service, name)

    def _write(self, name: str, value: str) -> None:
        self._keyring.set_password(self._service, name, value)

    def _remove(self, name: str) -> None:
        self._keyring.delete_password(self._service, name)


class UnavailableCredentialStore:
    """A store that holds nothing and says why.

    What `api.app.create_app` uses when no store was supplied. Deliberately
    not "the real one by default": a default that reached for this host's
    keyring would make every test that builds an app -- and the OpenAPI
    schema export -- depend on what the machine it runs on has installed,
    the same trap `ai_provider` avoids.
    """

    def __init__(self, reason: str) -> None:
        self._reason = reason

    def unavailable_reason(self) -> str | None:
        return self._reason

    def get(self, name: str) -> str | None:
        return None

    def set(self, name: str, value: str) -> None:
        raise CredentialStoreUnavailableError(self._reason)

    def delete(self, name: str) -> None:
        return None


class InMemoryCredentialStore:
    """A working store that outlives nothing. For tests only."""

    def __init__(self, initial: dict[str, str] | None = None) -> None:
        self._values = dict(initial or {})

    def unavailable_reason(self) -> str | None:
        return None

    def get(self, name: str) -> str | None:
        return self._values.get(name) or None

    def set(self, name: str, value: str) -> None:
        self._values[name] = value

    def delete(self, name: str) -> None:
        self._values.pop(name, None)


def create_credential_store() -> CredentialStore:
    """The real store for this host.

    Imported lazily so that neither a test nor the schema export pulls
    ``keyring`` (and, on Linux, its D-Bus machinery) into a process that will
    never ask it anything.
    """
    import keyring

    return KeyringCredentialStore(keyring)


def unavailable_store_reason(timeout_seconds: float) -> str:
    """The sentence a store that did not answer in time reports.

    Fixed words and the bound only -- never anything the backend said, for the
    reason the module docstring gives.
    """
    return f"{_UNAVAILABLE_PREFIX}（{timeout_seconds:.0f}秒以内に応答がありませんでした）"


def acquire_credential_store(
    build: Callable[[], CredentialStore],
    *,
    timeout_seconds: float = CREDENTIAL_STORE_TIMEOUT_SECONDS,
) -> CredentialStore:
    """``build()``'s store if it answers within ``timeout_seconds``, else one
    that says why (Issue #429).

    ``build`` is `create_credential_store` in production; it is a parameter so
    a test can state which world it is in -- a backend that answers, one that
    never does -- without importing ``keyring``.

    **Why a thread, not a shorter import or an alarm.** The measured failure
    is not a slow *call*: on a Linux host with a D-Bus session, ``import
    keyring`` itself never returns. The module's top-level code opens the
    session bus and waits for the Secret Service with no bound, so a timeout
    around a call cannot fire while the interpreter is stuck inside the
    import, and a ``signal`` alarm could only kill this process -- the whole
    requirement is that the server keeps starting. A daemon worker can be
    abandoned instead: ``join(timeout_seconds)`` returns and startup carries
    on while the stuck thread stays parked, harmless, until exit.

    **The worker probes too.** ``build()`` returning does not prove the store
    works, and a read that waits on a desktop unlock prompt would hang startup
    exactly as the import does. ``unavailable_reason()`` is the first call
    every read path already makes, so forcing it here means the returned store
    has either answered for real or been replaced by
    :class:`UnavailableCredentialStore`.

    An exception from ``build()`` is re-raised on the calling thread, so a
    genuinely broken import (``keyring`` missing from a bundle) still fails
    startup loudly instead of masquerading as a timeout.
    """
    outcome: list[CredentialStore] = []
    failure: list[BaseException] = []

    def _acquire() -> None:
        try:
            store = build()
            store.unavailable_reason()
        except Exception as exc:  # re-raised on the calling thread
            failure.append(exc)
            return
        outcome.append(store)

    worker = threading.Thread(target=_acquire, name="credential-store", daemon=True)
    worker.start()
    worker.join(timeout_seconds)
    if outcome:
        return outcome[0]
    if failure:
        raise failure[0]
    return UnavailableCredentialStore(unavailable_store_reason(timeout_seconds))
