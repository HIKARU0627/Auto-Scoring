"""``AIProvider`` for a host where no grading provider could be built.

Replaces `NullAIProvider` (Issue #20), which answered every request with
score 0, confidence 0.0 and a "未設定" rationale. That was an honest
*placeholder* while no real adapter existed at all. Once
`auto_scoring.adapters.ai_grading.factory.create_ai_provider` is actually
wired into the sidecar (Issue #97), the only way to still land here is a
host where not one transport has usable credentials -- and there, the
persisted `GradeResult` that placeholder produced is exactly the outcome
Issue #97 exists to remove: a row reading "0点 / confidence 0.0" is
indistinguishable, in the review UI, from a real provider that read the
answer and awarded nothing.

So this one raises instead of answering. `auto_scoring.jobs.
grading_processor.GradingJobProcessor` maps a bare `ProviderUnavailable` to
`ErrorCategory.PERMANENT`: the question's Job ends FAILED, is not retried
(no amount of retrying installs credentials on this machine), and no
`GradeResult` row is written at all.

The reason itself is not carried in that Job -- it is the same reason for
every question, and `GradingJobProcessor` deliberately keeps provider
exception text out of `Job.last_error` (AGENTS.md "Security"). It is stated
once, for the whole app, by ``GET /grading/availability``
(`auto_scoring.api.app`), which the app renders as a banner above every
screen. :attr:`reason` is the text that endpoint returns, and it therefore
must never contain a credential -- see `api.app.build_ai_provider`, the only
production caller, for how that is guaranteed.
"""

from __future__ import annotations

from typing import NoReturn

from auto_scoring.domain.ai_provider import (
    GradingRequest,
    ProviderDescriptor,
    ProviderUnavailable,
)


class UnconfiguredAIProvider:
    """Always raises `ProviderUnavailable`; never calls a network."""

    name = "unconfigured"

    def __init__(self, reason: str) -> None:
        self._reason = reason

    @property
    def reason(self) -> str:
        """Why no provider could be built, in terms an operator can act on.

        Names configuration *variables* and host prerequisites, never their
        values (`auto_scoring.adapters.ai_grading.factory`'s own rule for
        `AIProviderConfigError`).
        """
        return self._reason

    def describe(self) -> ProviderDescriptor:
        """The port requires a descriptor even from an adapter that never
        answers. Every field is the literal "unconfigured" rather than a
        plausible-looking model name, so a descriptor that somehow reached a
        record could not be mistaken for a real grading configuration."""
        return ProviderDescriptor(
            provider=self.name,
            model="unconfigured",
            version=None,
            prompt_version="unconfigured",
            temperature=0.0,
            structured_output_mode="none",
        )

    def grade(self, request: GradingRequest) -> NoReturn:
        raise ProviderUnavailable(f"no AI grading provider is configured: {self._reason}")
