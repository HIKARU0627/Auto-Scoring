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
