# PoC 4 — multi-layout profile generation / reapplication harness

Supports GitHub issue #15. Not imported by the app.

`report.py` regenerates the round-trip report and sample PDFs under
`docs/poc-4-multi-layout-profiles/`. Run it from `backend/`:

```
uv run python poc/issue_15_multi_layout_profile/report.py
```

For each fixture format it builds separate model-answer and grading-manual
PDFs. Together they contain all six marker kinds: question / answer area /
annotation area / score / rubric / model answer (tagged PDF annotations; see
`auto_scoring.domain.profile_detection`). It generates unconfirmed candidates,
simulates one human correction, confirms, then reapplies the profile to five
jittered student-answer PDFs of the same format and tabulates the drift. It
also runs the hard-to-detect fixture through the manual-fallback path.

The pass/fail check itself lives in
`backend/tests/test_profile_round_trip.py` -- this script only produces the
human-inspectable evidence. See `docs/poc-4-multi-layout-profiles.md` for the
decision record.
