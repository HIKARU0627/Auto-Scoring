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
      "ocr_clean": { "<raw AIGradingResult JSON, or an intentionally invalid object>": "...", "latency_seconds": 1.1, "cost_usd": 0.0009 },
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

A `recorded` entry that is missing a required field (see
`auto_scoring.domain.ai_grading.AIGradingResult`) is a deliberate
schema-violation fixture: the harness must count it toward
`schema_violation_rate`, never score it as a real grade.
