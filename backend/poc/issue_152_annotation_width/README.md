# Issue #152 — Annotation width & multi-line token union measurement

Supports GitHub Issue #152. Not imported by the app.

`report.py` measures real annotation widths and token unions on the live-run #6 dataset
(`appdata/database.sqlite`), isolating the root cause of oversized marks. Run it from `backend/`:

```sh
# Synthetic self-test (runs anywhere, no external data needed):
uv run python poc/issue_152_annotation_width/report.py --self-test

# Live-run data measurement:
uv run python poc/issue_152_annotation_width/report.py --data /home/hikaru/lv6/
```

See `docs/pdf-export.md` §2.6 for the full analysis, quantitative measurements, and architectural decision.
