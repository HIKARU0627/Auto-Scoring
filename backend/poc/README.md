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

The live-provider path (calling the adopted OCR service -- Google Document AI
since Issue #81 -- and recording `OcrResult`s) must be added to this PoC before
Issue #13 is closed, once credentials and the dataset are available. Only the selected adapter and
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

## Issue #25 -- queue throughput vs. the concurrency cap (`issue_25_queue_throughput/report.py`)

Measures how long the queue takes to drain a batch of synthetic answers at
several concurrency caps, given an assumed per-call provider latency. Feeds
**decision E** (並列 AI 処理数) in
[`docs/business-rules-and-evaluation-data.md`](../../docs/business-rules-and-evaluation-data.md)
§3 -- as evidence only. The decision is the project owner's, and its remaining
inputs (the chosen provider's rate limit, the real per-answer processing time,
a real error rate) need decisions A/B and Issue #35's measurements against a
real provider. Results and how to read them:
[`docs/mvp-acceptance.md`](../../docs/mvp-acceptance.md) §5.

```bash
# From backend/. Fully synthetic -- generated answer PDFs, stand-in providers,
# a temp app-data directory. No credentials, no real data.
uv run python poc/issue_25_queue_throughput/report.py
uv run python poc/issue_25_queue_throughput/report.py --answers 6 --latency 1.0
```

## Issue #130 -- scan-to-scan drift of the same printed form (`issue_130_scan_drift/`)

Measures how far the printed ruling of one answer form moves between two
separate scans of it, split into rotation, translation and scale -- the
systematic error behind detecting answer areas on one document and cropping
them out of another. Result, denominator, decision and the removal/promotion
condition: [`docs/poc-5-scan-to-scan-drift.md`](../../docs/poc-5-scan-to-scan-drift.md).

```bash
# From backend/. Synthetic only -- calibrates the probe against known
# transforms, so the real numbers can be read against its own error. No data.
uv run python poc/issue_130_scan_drift/report.py --self-test

# Against the licensed grading material (kept outside this repository; the
# path is an argument, never a default). Prints counts and displacements only.
uv run python poc/issue_130_scan_drift/report.py --data "<local grading-material dir>"
```
