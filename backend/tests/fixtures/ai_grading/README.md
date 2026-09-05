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
provider output for every `(provider, input_variant)` cell:

```jsonc
{
  "ground_truth": {
    "question_id": "opaque id, no PII",
    "subject": "arbitrary subject label",
    "test_id": "opaque id",
    "score": 15,
    "max_score": 20,
    "criteria": [{ "criterion_id": "c1", "outcome": "pass | partial | fail" }]
  },
  "input": {
    "prompt_text": "...",
    "model_answer": "...",
    "rubric_text": "...",
    "max_score": 20,
    "ocr_clean": "human-corrected reading of the answer",
    "ocr_noisy": "a plausible OCR misreading of the same answer (hand-authored -- no OCR pipeline exists yet, Issue #19)"
  },
  "recorded": {
    "<provider name>": {
      "ocr_clean": {
        "response": "<raw AIGradingResult JSON, or an intentionally invalid object>",
        "descriptor": {
          "model": "...",
          "version": "... or null",
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

A `recorded` entry whose `response` is missing a required field (see
`auto_scoring.domain.ai_grading.AIGradingResult`) is a deliberate
schema-violation fixture: the harness must count it toward
`schema_violation_rate`, never score it as a real grade. A `response` that
parses but answers a different question (`questionId` or `maxScore` not
matching this file's `ground_truth`) is a deliberate "mismatched" fixture --
counted toward `mismatch_rate`, and likewise never scored as a real grade,
since comparing raw scores alone could otherwise count an answer to the
wrong question as an accidental match.

`descriptor` is required on every cell that has a `response` -- the harness
reads it instead of fabricating one, so two cells recorded under different
settings for the same `provider` name stay distinguishable
(Issue #14 "再現条件"). A cell that intentionally demonstrates a schema
violation may omit `descriptor` (it is never reached, since the response
fails to parse before `descriptor` is read).
