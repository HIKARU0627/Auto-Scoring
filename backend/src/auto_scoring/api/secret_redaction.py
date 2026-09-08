"""One definition of "a configuration value must not be published", shared by
every channel that publishes text (Issue #97, review rounds 1 and 2).

Two leaks were found in this Issue, by two different routes:

1. a configuration error's message, which `api.app.build_ai_provider` turns
   into `UnconfiguredAIProvider.reason` and ``GET /grading/availability``
   returns to the app (round 1: an unparseable
   ``AUTO_SCORING_AI_GRADING_TEMPERATURE`` was quoted back verbatim);
2. a request URL, which the Vertex adapter builds out of
   ``AUTO_SCORING_VERTEX_PROJECT``/``AUTO_SCORING_GEMINI_MODEL`` and httpx
   logs at INFO into a file log that outlives the session (round 2).

Both are the same accident -- an operator pastes an API key into the wrong
variable -- and neither was a route anyone set out to build. Round 2's
question was the right one: rather than keep enumerating routes (a header, a
retry diagnostic, an exception's ``__cause__`` chain next), gate the two
places text actually leaves this process. `api.sidecar.install_log_redaction`
is the only place this process configures logging, and
`api.app.build_ai_provider` is the only place a reason is published; both
apply :func:`redact` with :func:`configuration_secrets`.

This is a safety net, not a licence: a message that quotes a configuration
value is still a bug (`adapters.ai_grading.factory`'s module docstring
forbids it), because the net only knows the values this process was
configured with.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence

#: Length at or above which *any* configuration value is treated as a secret,
#: regardless of which variable it came from.
#:
#: The threshold, rather than a list of "the sensitive variables", is the
#: whole point: round 2's leak was a key in ``AUTO_SCORING_VERTEX_PROJECT``,
#: which no name-based list would have covered. Every real API key is far
#: longer than this; what it spares is the short, structural configuration a
#: log is unreadable without -- ``v1``, ``0.0``, ``global``, ``codex``.
_MIN_SECRET_VALUE_LENGTH = 12

#: Variables whose value is a credential whatever its length -- a truncated
#: or test credential must not become publishable by being short.
_CREDENTIAL_VARIABLE_SUFFIXES = ("_API_KEY", "_KEY", "_TOKEN", "_SECRET", "_PASSWORD")

#: The configuration namespace this process owns. Nothing outside it is
#: scanned: ``PATH`` and the like are the host's, not this app's, and
#: redacting them would wreck the log to protect something this process never
#: sent anywhere.
_CONFIGURATION_PREFIX = "AUTO_SCORING_"

REDACTED = "***"


def configuration_secrets(environment: Mapping[str, str]) -> tuple[str, ...]:
    """The configuration values this process must never publish.

    ``environment`` is a parameter, never read from `os.environ` here: a
    default that reached for the real environment would make every test that
    installs logging or builds a provider depend on what the machine happens
    to export (docs/quality-gates.md).
    """
    secrets: set[str] = set()
    for name, raw in environment.items():
        if not name.startswith(_CONFIGURATION_PREFIX):
            continue
        value = raw.strip()
        if not value:
            # An empty pattern would rewrite every character of every line.
            continue
        if len(value) >= _MIN_SECRET_VALUE_LENGTH or name.endswith(_CREDENTIAL_VARIABLE_SUFFIXES):
            secrets.add(value)
    # Longest first, so a value that contains another is replaced whole
    # rather than leaving the tail of it behind.
    return tuple(sorted(secrets, key=len, reverse=True))


def redact(text: str, secrets: Sequence[str]) -> str:
    """``text`` with every secret in it replaced by :data:`REDACTED`."""
    for secret in secrets:
        if secret:
            text = text.replace(secret, REDACTED)
    return text
