# OCR PoC 1 sample fixtures

Synthetic, hand-authored samples used by `test_ocr_metrics.py` and as the
default dataset for `backend/poc/run_ocr_eval.py`. They let the metric pipeline
and the aggregate "結果表" be reproduced with **no credentials and no real
student data** (Issue #13 verification).

These are **not** real answers. No student-identifying data, no licensed
evaluation set, and no provider request/response bodies live here. The real
evaluation dataset is org-managed and stays outside the repo
(`docs/business-rules-and-evaluation-data.md` section 6.5).

## File shape

Each `sample-*.json` is one question-region sample:

```jsonc
{
  "ground_truth": {
    "sample_id": "opaque id, no PII",
    "reference_text": "human transcription of the region",
    "keywords": ["重要語", "..."],
    "handwriting_quality": "clean | normal | messy",
    "layout_type": "single_sheet | booklet | two_column | separate_answer",
    "expected_boxes": [{ "x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0 }]
  },
  "ocr_result": {
    "text": "recorded provider text (empty string = failed read)",
    "provider": "recorded-fixture",
    "tokens": [
      {
        "text": "光合成",
        "bounding_box": { "x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0 },
        "confidence": 0.0,
        "band": "high | medium | low"
      }
    ]
  }
}
```

Coordinates are normalised to `0.0..1.0`. An unreadable span is recorded as a
`low`-band token with a best-guess `text`, never omitted.
