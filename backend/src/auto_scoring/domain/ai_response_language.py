"""The one place that says what language an AI provider's natural-language
output must be written in (Issue #140).

Commander decision: fixed to Japanese, not configurable. Every user of this
app is a Japanese cram-school teacher reading a rationale, a comment, or an
extraction note as a draft of what they will hand back to a student -- there
is no other audience to switch the setting for.

**Why one constant instead of three adapters each saying it their own way.**
A real 8-subject run returned ``rationale``/``comment`` in English for three
subjects (日本史・化学・英語) and in Japanese for the other three
(古漢・現代文・生物): the model was following the language of the material
it was given -- an English exam question, or the surrounding source
document -- because nothing told it to do otherwise. The same run's
criteria-extraction warnings (the model's own ``note``) came back in English
too and went straight to the teacher's screen. Three adapters writing this
instruction separately is exactly how it drifts: the fix is one sentence,
defined once, that every adapter's prompt and every human-facing schema
field description quotes instead of retyping (docs/ai-grading-pipeline.md).

**Why both the prompt text and the field description.** A structured-output
backend enforces the *schema*, including each field's own ``description``;
the free-text system/developer instructions travel over a separate channel
that nothing requires a schema-driven decoder to have weighed as heavily.
Stating the language rule in only one of the two lets a model default back
to the material's language for whichever field the other channel did not
reach -- which is the failure mode this Issue was filed against, not a
hypothetical one.

**What this does not cover.** Quoted material -- the student's own answer,
the model answer, a verbatim OCR excerpt -- is not translated: translating a
quotation would corrupt the very text the app matches back to the source
page (see ``domain.ai_grading.AnnotationCandidate.target``, which is exempt
by design and carries its own description instead of this one).
"""

from __future__ import annotations

#: One sentence, meant to be appended to each adapter's own system/developer
#: instructions (`adapters.ai_grading._prompt.GRADING_SYSTEM_INSTRUCTIONS`,
#: `adapters.criteria_extraction._prompt.CRITERIA_SYSTEM_INSTRUCTIONS`,
#: `adapters.answer_area_detection._prompt.ANSWER_AREA_SYSTEM_INSTRUCTIONS`).
RESPONSE_LANGUAGE_INSTRUCTION = (
    "Write every field that is your own explanation, judgement, or note (for "
    "example: rationale, comment, note) in Japanese, regardless of the "
    "language of the question, the source material, or the student's "
    "answer. Text you quote verbatim from the source material or the "
    "student's answer stays in its original language -- do not translate a "
    "quotation."
)

#: One clause, meant to be appended to a schema field's own ``description``
#: for a field the model fills with its own prose (never for a field that
#: only quotes the material verbatim, such as ``target``).
FIELD_LANGUAGE_NOTE = " Write this field in Japanese."
