# backend/poc

Throwaway technical probes (`AGENTS.md` "Verification"). Code here is **not**
packaged into the sidecar wheel and **not** type-checked by `mypy`; it is still
linted and formatted by Ruff. Each probe is done only when its repro command,
expected result, actual result, decision, and removal-or-promotion condition are
recorded in `docs/`.

## PoC 1 -- Japanese handwriting OCR (`run_ocr_eval.py`)

Aggregates OCR metrics from recorded provider runs against human ground-truth
labels. Full plan, adoption criteria, and result table:
[`docs/poc-1-japanese-handwriting-ocr.md`](../../docs/poc-1-japanese-handwriting-ocr.md).

```bash
# From backend/. Runs on committed synthetic fixtures -- no credentials, no
# real data. Reproduces the secret-free aggregate table.
uv run python poc/run_ocr_eval.py

# Against the licensed evaluation dataset (recorded runs + human labels):
uv run python poc/run_ocr_eval.py --dataset "<local eval-dataset dir>" --out poc-1-results.md
```

The live-provider path (calling Google Cloud Vision / a second candidate and
recording `OcrResult`s) must be added to this PoC before Issue #13 is closed,
once credentials and the dataset are available. Only the selected adapter and
its contract test are promoted afterward; see the doc's credentials and
promotion sections.

## PoC 2 -- AI grading accuracy and structured output (`issue_14_ai_grading/report.py`)

Aggregates AI grading metrics (exact match / within-tolerance / criterion
agreement / schema violation rate / latency / approximate cost) from recorded
provider responses against human ground-truth scores. Full plan, adoption
criteria, and result table:
[`docs/poc-2-ai-grading.md`](../../docs/poc-2-ai-grading.md).

```bash
# From backend/. Runs on committed synthetic fixtures -- no credentials, no
# real data. Reproduces the secret-free aggregate table.
uv run python poc/issue_14_ai_grading/report.py

# Against the licensed evaluation dataset (recorded runs + human labels):
uv run python poc/issue_14_ai_grading/report.py --dataset "<local eval-dataset dir>" --out poc-2-results.md
```

Structured output is validated by
`auto_scoring.domain.ai_grading.AIGradingResult` (Pydantic): score, criterion
result, comment, rationale (根拠), and Grading Confidence are all schema
fields, and Recognition Confidence never shares a field with Grading
Confidence. A response that fails validation is a schema violation, never a
free-text-parsed guess. The live-provider path (calling Gemini / Claude / GPT
and recording `AIGradingResult`s) must be added to this PoC before Issue #14
is closed, once credentials are available. Only the selected adapter(s) and
the `AIProvider` contract test are promoted afterward; see the doc's
credentials and promotion sections.
