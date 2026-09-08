"""The ordered fallback chain decided in Issue #81, as one ``AIProvider``.

business-rules-and-evaluation-data.md section 3 (B): the adopted
configuration is not a single model but a priority order -- ① Gemini API
(Vertex AI) -> ② Codex App Server -> ③ OpenRouter -> ④ OpenAI API -- tried
top to bottom until one of them grades the question.

``docs/ai-grading-pipeline.md`` "AIモデル: 優先度つきフォールバック" fixes
where this layer lives and why it is *here*, inside the ``AIProvider`` port,
rather than in ``GradingJobProcessor`` or the queue's retry layer:

* in the processor, a provider-selection loop would mix into steps 6-8,
  which are written around "one provider call";
* in the queue's retry layer, every fallback would consume a ``Job``
  attempt, conflating "back off and retry the same provider" (waiting for a
  rate limit to clear) with "switch to a different provider" (not waiting
  at all) -- two different things;
* as a composite adapter it is one more ``AIProviderContract`` subclass and
  reuses the existing ``create_app(ai_provider=...)`` injection point
  unchanged.
"""

from __future__ import annotations

from collections.abc import Sequence

from auto_scoring.domain.ai_provider import (
    AIProvider,
    GradingRequest,
    GradingResponse,
    ProviderDescriptor,
    ProviderUnavailable,
    SchemaViolation,
)


class FallbackAIProvider:
    """Tries each child in order until one grades the question.

    Falls through on exactly the failures ``docs/ai-grading-pipeline.md``
    lists as fall-through, which is every failure this port can raise:

    * ``ProviderRateLimitedError`` (429) -- moving on is faster than waiting
      for this provider's quota to free up;
    * ``ProviderServerError`` (5xx) and ``ProviderTimeoutError`` -- a
      provider-side outage; re-sending to the same provider tends to
      reproduce it, so there is no in-provider retry here, just one attempt
      each;
    * ``SchemaViolation`` -- a model-capability difference. Re-sending to
      the *same* model will not fix it, but another model may well comply;
    * a bare ``ProviderUnavailable`` (an auth/config 4xx, a transport
      error). Not in the document's table, which only covers configuration
      problems detectable at *construction* time
      (``AIProviderConfigError``, excluded by ``factory.create_ai_provider``
      before the chain is built). A credential that was valid at
      construction and is rejected at call time is exactly the case this
      chain exists for, so it falls through too.

    Notably absent: a response/label correspondence mismatch (step 7,
    criterion-id disagreement). That is judged outside this port, by
    ``GradingJobProcessor``, and stays ``PERMANENT`` -- the chain never sees
    it.

    **Anything else propagates and stops the chain, deliberately.** That
    list is exactly the exception contract ``domain.ai_provider.AIProvider``
    declares, so an exception outside it is an adapter bug, not a provider
    outage -- and routing around a bug is how a provider stays broken for
    months without anyone noticing, since a chain that recovers reports
    nothing. It also would not be one provider's bug: the same malformed
    body that trips one adapter would trip it on every request, so the
    "recovery" is really "silently run on the second-choice model forever".
    The place that failure gets fixed is the adapter boundary, where each
    one turns an arbitrary remote body into one of the two declared
    exceptions -- see the malformed-envelope tests in each adapter's
    contract test (code review finding: three separate ways for the chain
    to stop early all turned out to be adapters leaking an undeclared
    exception, not the chain being too strict).

    When every child has failed, **the last observed exception is re-raised
    unchanged**, so the queue keeps classifying it exactly as it would
    without a chain (``jobs.grading_processor``: timeout/429/5xx stay
    retryable ``ErrorCategory`` values and the job backs off; an all-
    ``SchemaViolation`` chain becomes ``PERMANENT`` and goes to a human).
    """

    name = "fallback"

    def __init__(self, providers: Sequence[AIProvider]) -> None:
        if not providers:
            raise ValueError("FallbackAIProvider requires at least one provider")
        self._providers = tuple(providers)
        #: Which child ``describe()`` reports. Starts at the first child
        #: (what the next call will try) and follows each attempt, so after
        #: a fully-failed ``grade()`` it names the child that produced the
        #: exception the caller received -- rather than a provider that was
        #: never reached, or one that succeeded on some earlier call.
        self._last_attempted: AIProvider = self._providers[0]

    @property
    def providers(self) -> tuple[AIProvider, ...]:
        """The chain in priority order (highest priority first)."""
        return self._providers

    def describe(self) -> ProviderDescriptor:
        """The descriptor of the child last attempted (initially the first).

        This is *not* the identity a result is recorded under: ``grade()``
        returns the successful child's own ``GradingResponse``, descriptor
        included, so ``GradeResult.provider``/``model``/``prompt_version``
        name the provider that actually graded (decision record section 3
        (B): "どの provider で採点したかを結果に残す"). This chain's own
        ``name`` deliberately never overwrites it -- provider-level
        agreement metrics (``domain.ai_grading_metrics``) only mean anything
        if each result stays attributed to the model that produced it.
        """
        return self._last_attempted.describe()

    def grade(self, request: GradingRequest) -> GradingResponse:
        last_failure: Exception | None = None
        for provider in self._providers:
            self._last_attempted = provider
            try:
                return provider.grade(request)
            except (ProviderUnavailable, SchemaViolation) as exc:
                # Never logged and never wrapped: the exception messages
                # from these adapters are already body-free (AGENTS.md
                # "Security"), and re-raising the original unchanged at the
                # end of the chain is what keeps the queue's existing
                # error classification correct.
                last_failure = exc
        assert last_failure is not None  # the loop runs at least once (non-empty chain)
        raise last_failure
