# PoC 2 -- AI grading accuracy and structured output

Supports GitHub issue #14 (parent #3). Not imported by the app.

`report.py` aggregates AI grading metrics (exact match / within-tolerance /
criterion agreement / schema violation rate / latency / approximate cost)
from recorded provider responses and human ground-truth labels. Run it from
`backend/`:

```
uv run python poc/issue_14_ai_grading/report.py
```

With no `--dataset`, it reads the committed synthetic fixtures under
`tests/fixtures/ai_grading/` -- invented questions, rubrics, and provider
responses, safe to commit, used only to prove the pipeline reproduces the
same aggregate table from the same input every time (Issue #14
verification). Point `--dataset` at a local, licensed real-data directory
(never inside this repository) for real numbers:

```
uv run python poc/issue_14_ai_grading/report.py --dataset "<local eval-dataset dir>" --out poc-2-results.md
```

See `docs/poc-2-ai-grading.md` for the decision record: comparison
candidates, the Pydantic schema boundary
(`auto_scoring.domain.ai_grading.AIGradingResult`), the adoption thresholds,
the real-data pilot's scope and limits, and the result table.

A cell with no recorded `response` yet (a real sample staged ahead of a
provider run) is counted as "pending", not scored as zero. A cell whose raw
JSON fails schema validation is a schema violation -- it is never
free-text-parsed into a guessed grade (Issue #14 acceptance).

## `record.py` -- the live-provider path (Issue #35)

Calling a real provider to populate `recorded` is what `report.py` never
did. `record.py` is that half:

```
uv run --env-file .env.local python poc/issue_14_ai_grading/record.py \
    --dataset "<local eval-dataset dir>" --images "<local crops dir>" \
    [--variant ocr_clean|ocr_noisy|both] [--limit N] [--overwrite] [--dry-run]
```

Which provider it calls comes from `AUTO_SCORING_AI_GRADING_TRANSPORT` (a
comma-separated priority list -- the Issue #81 fallback chain), via
`adapters.ai_grading.factory.create_ai_provider()`; each cell is filed under
the provider that actually answered. `--images` holds the answer-region
crops the dataset's `input.answer_image_ref` values name, and a
`sha256:<hex>` reference is verified against the bytes read.

**It records nothing it cannot verify.** The rule is an allowlist, not a
list of fields known to hold prose: a provider-supplied value is written
only when it is a value this run sent and matched back (`questionId`,
`criteria[].id`, the descriptor's configured strings), or constrained by
type and range (numbers, enums). Everything else becomes a fixed marker,
and the one response-derived piece of metadata (`descriptor.version`)
becomes a content-free `sha256` fingerprint that still keeps two
deployments in two buckets. Schema validation is not anonymization -- it
checks a value's *shape* and says nothing about its content, so "this field
is an id" is not a safety argument -- and Issue #35's acceptance condition
is that answer text stays out of the *output*, not just out of the
repository.

It also refuses to record into any dataset inside this repository (a real
provider's response body must never reach a commit), never puts an
unvalidated `answer_image_ref` into an error message, records a schema
violation or an exhausted retry explicitly rather than fabricating a grade,
and prints no student content.

`--dry-run` validates a dataset and its crops with no credentials and no
calls. `docs/poc-2-ai-grading.md` section 4.3 documents the design, section
7.4 the live probe results.

**The bundled fixtures include `tests/fixtures/ai_grading/images/`** -- one
synthetic 8x8 PNG per sample, named by its own sha256 so the committed
`answer_image_ref` values are internally consistent and the live path can be
rehearsed offline (copy the fixtures out of the repository first).
