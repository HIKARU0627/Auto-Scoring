# AI grading PoC 2 sample fixtures

Synthetic, hand-authored samples used by `test_ai_grading_metrics.py` and as
the default dataset for `backend/poc/issue_14_ai_grading/report.py`. They let
the schema-validation + metrics pipeline and the aggregate "結果表" be
reproduced with **no credentials and no real student data**
(Issue #14 verification: "secretと答案本文を出力せず、同じデータから
集計結果を再生成できることを確認する").

These are **not** real questions, rubrics, or answers -- everything here is
invented for pipeline testing. No student-identifying data, no licensed
evaluation set, and no real provider request/response bodies live here.
Provider names (`synthetic-a` / `synthetic-b`) are placeholders, not real
vendor identifiers. The real evaluation dataset (manually transcribed from
licensed exam material) stays outside the repo
(`docs/business-rules-and-evaluation-data.md` section 6.5).

## File shape

Each `sample-*.json` is one graded question, with recorded (invented)
provider output for every `(provider, input_variant)` cell. `ground_truth`
follows the wire schema `business-rules-and-evaluation-data.md` section 6.3
documents for a real human-grader label file (`questionId` / `score` /
`maxScore` / `criteria[].{id,result}` / `source`, plus the optional `comment`
/ `annotations` / `handwritingQuality` / `layoutType`), so a real label file
produced per that section can be loaded as-is -- `subject` is deliberately a
sibling of `ground_truth`, not a field inside it, since section 6.3's
per-answer label schema has no `subject` field (it is test-level metadata,
section 6.1). A `ground_truth` model that instead invented its own field
names and forbade the documented ones rejected every correctly-formed real
label file outright, making the real-data harness impossible to run at all
(code review finding).

`source` is required and must be the literal `"human"` -- section 6.3's
label procedure always attaches it to a genuine label, and it is the one
field that tells a real human-grader label apart from an AI-generated
response mistakenly fed in as if it were ground truth (an omitted or
`"ai"` `source` is rejected; code review finding).

`submissionId` is likewise a required, non-blank sibling field: section 6.3
identifies each real answer sheet by a non-PII `submissionId`, and one real
submission commonly spans several questions, each its own sample file here.
Without it the harness cannot tell "30 distinct submissions" (section 6.2's
minimum dataset size) apart from "30 questions on 6 submissions" --
`questionId` alone identifies which question, not which answer sheet it
came from (code review finding). The aggregate report includes a distinct-
submission count per subject for exactly this coverage check.

```jsonc
{
  "subject": "arbitrary subject label",
  "submissionId": "opaque id, no PII -- identifies the answer sheet, not the question",
  "ground_truth": {
    "questionId": "opaque id, no PII",
    "score": 15,
    "maxScore": 20,
    "criteria": [{ "id": "c1", "result": "pass | partial | fail" }],
    "source": "human",
    "comment": "optional -- 確定コメント",
    "annotations": [],
    "handwritingQuality": "optional -- clean | normal | messy",
    "layoutType": "optional"
  },
  "input": {
    "prompt_text": "...",
    "model_answer": "...",
    "rubric_text": "...",
    "max_score": 20,
    "ocr_clean": "human-corrected reading of the answer (may be \"\" -- the student left the question blank)",
    "ocr_noisy": "a plausible OCR misreading of the same answer (hand-authored -- no OCR pipeline exists yet, Issue #19); may also be \"\""
  },
  "recorded": {
    "<provider name>": {
      "ocr_clean": {
        "response": "<raw AIGradingResult JSON, or an intentionally invalid object>",
        "descriptor": {
          "model": "...",
          "version": "... or null",
          "prompt_version": "...",
          "temperature": 0.0,
          "structured_output_mode": "json_schema | tool_use | ..."
        },
        "latency_seconds": 1.1,
        "cost_usd": 0.0009
      },
      "ocr_noisy": { "...": "..." }
    }
  }
}
```

`ocr_clean` and `ocr_noisy` are always evaluated as separate cells (never
averaged together): the harness records `recognition.confidence` and
`grading.confidence` from each response into separate summary columns, so a
reader never mistakes "text was read cleanly" for "the grade is trustworthy"
(simplified-design-specification.md section 10).

The **expected comparison matrix** is every provider name recorded anywhere
in the dataset, times both `ocr_clean` and `ocr_noisy` -- not just whatever
keys a given sample happens to define. A cell missing from that matrix (no
entry at all, or an entry with no `response` key) is "pending" in the
harness's output, never silently skipped, so an incomplete real dataset
cannot look like a completed comparison.

The harness additionally requires at least 2 providers to each have a real
recorded response **on a shared sample and input variant** before it will
report anything: an empty or all-pending `"<provider>": {}` placeholder does
not count as a candidate; two providers recorded only on disjoint samples
(never together on one question) do not count as a comparison; and two
providers recorded on the same question but under different variants (one
only on `ocr_clean`, the other only on `ocr_noisy`) do not count either --
those are different evaluation modes, not a comparison. A dataset that does
not meet this bar makes `report.py` exit non-zero with a message naming
which providers *did* qualify, rather than printing a table as if the
comparison were complete.

That dataset-wide check only gates whether the dataset has *any* real
comparison at all -- it is not enough to make every one of a qualifying
provider's cells safe to aggregate. A provider can overlap with another on
one sample while also carrying extra recorded responses on samples nobody
else ever answered; those extra responses are excluded one
`(sample, input_variant)` at a time and reported as a separate "excluded"
count, never silently pooled into that provider's own metrics as if they too
were part of a same-data comparison (code review finding: an earlier version
only checked overlap dataset-wide, so a provider's solo responses on
disjoint samples still got scored into its own aggregate exact-match/
criterion/confidence rates). With 3+ providers, requiring only ">= 2
responders" per cell is not enough either: if A and B answer sample X
together, and B and C answer a *different* sample Y together, both cells
pass an ">= 2" check even though A and C were never run on the same data at
all -- reporting all three side by side would let a difference in sample
difficulty masquerade as a difference in provider quality (code review
finding). A cell is only counted when its responders are *exactly* the
dataset-wide comparable set, not merely some 2-of-N subset of it -- and
that identity is `(provider, config_key)`, not provider name alone: a
provider that switches configuration between samples (A/v1 grades X, then
A/v2 grades Y, while B/v1 grades both) must not have its X and Y cells
treated as "the same candidate" just because the provider name matches,
since the results table buckets them into two different config rows drawn
from two different sample pools either way (code review finding;
docs/poc-2-ai-grading.md section 3.3's config-bucket separation).

Every raw `recorded` provider key is normalized (whitespace-stripped)
before it is counted as a candidate: `ProviderDescriptor` only rejects an
entirely blank name, so `"gemini"` and `"gemini "` would otherwise count as
two separate candidates for the same real provider, letting one
inconsistently-spelled key alone satisfy the >= 2 comparison gate (code
review finding). Two different raw keys that normalize to the same id are
rejected outright rather than silently merged.

Every provider's `recorded` entry may only use the two recognized
input-variant keys (`ocr_clean` / `ocr_noisy`) -- an unrecognized key (a
typo such as `"ocr_nosiy"`) makes the harness raise rather than silently
ignoring it: neither lookup used elsewhere in the harness iterates whatever
keys happen to be present, so a response recorded under a misspelled key
would otherwise never be found, leaving its cell "pending" forever while
the harness still exits 0 as if the aggregate were complete (code review
finding). The unrecognized key itself is never echoed in the raised
message (see below).

Each sample's `input` block is parsed and cross-checked against its
`ground_truth` (`max_score` must agree) before any of that sample's
`recorded` cells are scored -- a same-data comparison requires the
underlying question material, not just the final score, to actually match.
A sample missing `input`, or whose `input.max_score` disagrees with
`ground_truth.max_score`, makes the harness raise.

A `recorded` entry whose `response` is missing a required field (see
`auto_scoring.domain.ai_grading.AIGradingResult`) is a deliberate
schema-violation fixture: the harness must count it toward
`schema_violation_rate`, never score it as a real grade. A `response` that
parses but answers a different question (`questionId` or `maxScore` not
matching this file's `ground_truth`) is a deliberate "mismatched" fixture --
counted toward `mismatch_rate`, and likewise never scored as a real grade,
since comparing raw scores alone could otherwise count an answer to the
wrong question as an accidental match.

`descriptor` is required on every cell that has a `response` key -- including
one that intentionally demonstrates a schema violation. The harness reads and
strictly validates `descriptor` (`auto_scoring.domain.ai_provider.
parse_provider_descriptor`) *before* it attempts to parse `response`, so a
schema-violation fixture still needs a valid `descriptor` to be counted
toward `schema_violation_rate` under the right configuration bucket
(the config a violation was produced under still has to be attributable, so
it can be told apart from a different configuration's violations -- Issue #14
"再現条件"); omitting `descriptor` on such a cell makes the harness raise
(`_InvalidDescriptor`) rather than silently drop that cell from the aggregate
(code review finding: an earlier version of this note said such a cell "is
never reached" and could omit `descriptor` -- that was never actually true of
the loader's read order and would have crashed the whole run). A malformed
`descriptor` value (`model: null`, `temperature: true`, a blank string, ...)
is rejected rather than silently cast into something plausible-looking --
this holds even for a directly-constructed `ProviderDescriptor` (bypassing
this JSON boundary entirely), since `bool` is a subclass of Python's `int`
and would otherwise pass the finite/non-negative check silently (code
review finding). The
`config` column this produces is a JSON-array encoding of the five fields,
not a `"|"`-joined string -- a naive join would let two different
configurations collide whenever a field value itself contains `"|"`.
`temperature` is normalized (`float()`, and negative zero folded to
positive zero) before it is serialized into that key, so a descriptor built
directly with the Python int literal `0` produces the same `config` as the
same value loaded through this JSON boundary (which becomes `0.0`) -- two
equivalent configurations must not split into separate metric buckets just
because of which code path constructed the descriptor (code review
finding).

`latency_seconds` / `cost_usd` are validated as finite, non-negative numbers
before they reach any aggregate -- a negative, non-finite (`nan`/`inf`), or
non-numeric (string, boolean) recorded value makes the harness raise rather
than silently skew the adoption-gate metrics. The raised message never
embeds the value itself (only the field name and its type) -- it comes from
the same untrusted `--dataset` file as everything else, and a malformed
dataset could put arbitrary text there by mistake (code review finding).

A `recorded.<provider>.ocr_noisy` entry is rejected if this sample's
`input.ocr_noisy` is `null` -- a noisy-variant response with no corresponding
noisy input was never a real same-data comparison (code review finding).
Every sample's `ground_truth` and `input` are parsed and validated up front,
across *all* files, before the harness even checks whether any provider has
a real recorded response -- a dataset where every sample is still `"recorded":
{}` (the staged, no-credentials-yet case) is not exempt from this: an invalid
`ground_truth` (e.g. `score > max_score`) in a staged sample still makes the
harness raise, instead of being reported as a clean `staged: N` count (code
review finding). Any validation failure message is sanitized to the failing
field's path and error type only -- never the value that failed, since that
value may be OCR'd student answer text (`AGENTS.md` "Security"). The field
*path* itself is sanitized too: for an `extra_forbidden` error (an
unrecognized key on a strict model), pydantic's `loc` for that error is
exactly the offending key itself, copied verbatim from the untrusted
mapping -- a stray note accidentally left as a JSON key could carry real
student text straight into an otherwise "sanitized" message. Only the
final `loc` segment of such an error is ever untrusted, and it is replaced
with a fixed placeholder rather than echoed (code review finding).

A `response.annotations[]` entry with `type: "comment"` must carry a
non-blank `comment` -- a comment-kind annotation with nothing to say is
rejected as a schema violation at this boundary rather than surfacing as a
crash when `domain.models.Annotation` is built from it later (code review
finding).

Every text cell the results table renders that is derived from the dataset
(`subject`, `provider`, `config`) -- not just `config` -- is Markdown-escaped
before insertion: a literal `|` or newline in any of them would otherwise
open extra cells or start a new row partway through one (code review
finding).
