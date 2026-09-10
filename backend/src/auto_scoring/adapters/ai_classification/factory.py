"""Build the material classifier from the same configuration grading uses
(Issue #101).

`adapters.ai.image_transport` reads the same
``AUTO_SCORING_AI_GRADING_TRANSPORT`` priority list as
`adapters.ai_grading.factory`, and this builds a classifier over the first
transport in it that has usable credentials on this host. Sharing the
variable is deliberate: an operator who has configured grading has, by
definition, configured a provider that can also look at a page image, and a
second variable to keep in step would be a second thing to get wrong.

**No fallback chain.** Grading builds one because a failed grading call
blocks a whole submission; a failed *classification* call blocks nothing --
the file stays unresolved and the reviewer picks its role, which they can do
anyway. Adding a chain here would multiply the cost and the wait of the one
thing Issue #101 explicitly asks to keep cheap.

``codex_app_server`` is not supported: its protocol carries no image input,
and classification is entirely about looking at a page. A host configured
with only that transport gets :class:`ClassifierUnavailable` and the manual
path, which is the honest answer rather than a chain link that always fails.

No message raised from this module may quote a configuration *value* -- only
variable names and the fixed transport ids (the same rule
`adapters.ai_grading.factory` documents, for the same reason: this text is
published through the API and shown on screen).
"""

from __future__ import annotations

import os
from collections.abc import Mapping

from auto_scoring.adapters.ai.image_transport import (
    IMAGE_CAPABLE_TRANSPORTS,
    TRANSPORT_ENV_VAR,
    NoUsableTransport,
    TokenSourceFactory,
    default_token_source,
    select_image_capable_call,
    transport_priority_list,
)
from auto_scoring.adapters.ai_classification.classifier import (
    DEFAULT_TIMEOUT_SECONDS,
    SCHEMA_NAME,
    StructuredMaterialClassifier,
)
from auto_scoring.domain.material_classifier import ClassifierUnavailable, MaterialClassifier


def create_material_classifier(
    env: Mapping[str, str] | None = None,
    *,
    token_source_factory: TokenSourceFactory = default_token_source,
) -> MaterialClassifier:
    """The classifier for this host.

    Raises :class:`ClassifierUnavailable` -- carrying a reason safe to show
    on screen -- when nothing usable is configured. Callers treat that as
    "offer the manual path", never as a hard failure: role rules still work,
    and a reviewer assigning roles by hand is the same act they perform to
    confirm a proposal.
    """
    values = env if env is not None else os.environ
    transports = transport_priority_list(values)
    if not transports:
        raise ClassifierUnavailable(
            f"{TRANSPORT_ENV_VAR} is not set, so no AI classification is available on this host"
        )
    prompt_version = values.get("AUTO_SCORING_AI_GRADING_PROMPT_VERSION", "").strip()
    if not prompt_version:
        raise ClassifierUnavailable(
            "AUTO_SCORING_AI_GRADING_PROMPT_VERSION is required for AI classification"
        )

    try:
        call = select_image_capable_call(
            transports,
            values,
            token_source_factory=token_source_factory,
            schema_name=SCHEMA_NAME,
            temperature=0.0,
            timeout_seconds=DEFAULT_TIMEOUT_SECONDS,
        )
    except NoUsableTransport:
        # Deliberately not quoting `NoUsableTransport.skipped`: this reason
        # is shown next to a manual role picker, where "which transports were
        # tried" is noise -- what a reviewer needs is that classification is
        # off and the list of vendors that could turn it back on.
        raise ClassifierUnavailable(
            f"none of the transports listed in {TRANSPORT_ENV_VAR} can classify on this host; "
            f"AI classification needs one of {list(IMAGE_CAPABLE_TRANSPORTS)} with credentials"
        ) from None
    return StructuredMaterialClassifier(call, prompt_version=prompt_version)
