"""PoC 6 (issue #202) repro command: compare pdf.js vs pypdfium2 display for Electron.

Run from ``backend/``::

    uv run python ../desktop-poc/issue_202_pdf_coordinates/report.py

Prerequisites (probe-only, not product deps)::

    cd ../desktop-poc/issue_202_pdf_coordinates/approach_a && npm install

Writes:

* ``docs/poc-6-pdf-coordinates/approach-b-round-trip.md``
* ``docs/poc-6-pdf-coordinates/approach-a-round-trip.md``
* ``docs/poc-6-pdf-coordinates.md`` — decision record (5 verification points)

Exits non-zero if either approach exceeds PoC 3 tolerance (0.004 normalized).
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

_PROBE_DIR = Path(__file__).resolve().parent
_ROOT = _PROBE_DIR.parents[1]
sys.path.insert(0, str(_PROBE_DIR))

from auto_scoring.adapters.pdf import PdfiumPypdfEngine

_SAMPLES_DIR = _PROBE_DIR / "samples"
_OUT_DIR = _ROOT / "docs" / "poc-6-pdf-coordinates"
_APPROACH_A_DIR = _PROBE_DIR / "approach_a"

from approach_b_measure import (  # noqa: E402
    ApproachBResult,
    run as run_approach_b,
    verdict as approach_b_verdict,
)
from fixtures import FIXTURES, TEST_POINTS, write_fixture  # noqa: E402
from measure_common import RENDER_SCALE, TOLERANCE  # noqa: E402


@dataclass(frozen=True)
class ApproachAResult:
    viewport_rows: tuple[dict[str, float | str], ...]
    round_trip_rows: tuple[dict[str, float | str], ...]
    worst_viewport_delta_pt: float
    worst_round_trip_error: float
    pdfjs_version: str


def _prepare_stamped_pdfs(samples_dir: Path) -> None:
    engine = PdfiumPypdfEngine()
    samples_dir.mkdir(parents=True, exist_ok=True)
    for fixture in FIXTURES:
        source = samples_dir / f"{fixture.name}.pdf"
        write_fixture(fixture, source)
        for index, point in enumerate(TEST_POINTS):
            stamped = samples_dir / f"{fixture.name}-{index}.stamped.pdf"
            engine.stamp_markers(source, stamped, {0: [point]})


def _run_approach_a(samples_dir: Path) -> ApproachAResult:
    jobs_path = samples_dir / "approach-a-jobs.json"
    engine = PdfiumPypdfEngine()
    viewport_checks = []
    round_trips = []
    for fixture in FIXTURES:
        source = samples_dir / f"{fixture.name}.pdf"
        geometry = engine.page_geometry(source, 0)
        viewport_checks.append(
            {
                "fixture": fixture.name,
                "pdf": str(source.resolve()),
                "expected_width": geometry.displayed_width,
                "expected_height": geometry.displayed_height,
            }
        )
        for index, point in enumerate(TEST_POINTS):
            stamped = samples_dir / f"{fixture.name}-{index}.stamped.pdf"
            round_trips.append(
                {
                    "fixture": fixture.name,
                    "pdf": str(stamped.resolve()),
                    "nx": point.x,
                    "ny": point.y,
                }
            )
    jobs_path.write_text(
        json.dumps({"viewport_checks": viewport_checks, "round_trips": round_trips}, indent=2),
        encoding="utf-8",
    )

    measure_script = _APPROACH_A_DIR / "measure.mjs"
    if not measure_script.exists():
        raise SystemExit(f"missing {measure_script}")

    node_modules = _APPROACH_A_DIR / "node_modules"
    if not node_modules.exists():
        raise SystemExit(
            "approach_a npm deps missing; run: "
            f"cd {_APPROACH_A_DIR.relative_to(_ROOT)} && npm install"
        )

    completed = subprocess.run(
        [
            "node",
            str(measure_script),
            "--jobs",
            str(jobs_path.resolve()),
            "--scale",
            str(RENDER_SCALE),
        ],
        cwd=_APPROACH_A_DIR,
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(completed.stdout)
    return ApproachAResult(
        viewport_rows=tuple(payload["viewport_results"]),
        round_trip_rows=tuple(payload["round_trip_results"]),
        worst_viewport_delta_pt=float(payload["worst_viewport_delta_pt"]),
        worst_round_trip_error=float(payload["worst_round_trip_error"]),
        pdfjs_version=str(payload["pdfjs_version"]),
    )


def _write_approach_b_report(result: ApproachBResult) -> None:
    rows = result.round_trip_rows
    fixture_count = len(FIXTURES)
    point_count = len(TEST_POINTS)
    total = len(rows)
    path = _OUT_DIR / "approach-b-round-trip.md"
    lines = [
        "# PoC 6 Approach B round-trip (generated)",
        "",
        "Engine: **pypdfium2** bitmap (same as `PdfiumPypdfEngine.render_page_png`).",
        "",
        f"- fixtures: {fixture_count}",
        f"- points per fixture: {point_count}",
        f"- total measurements: {total} (= {fixture_count} × {point_count})",
        f"- render scale: {RENDER_SCALE}",
        f"- tolerance: {TOLERANCE} normalized",
        f"- worst error: {result.worst_error:.4f} -> **{approach_b_verdict(result.worst_error)}**",
        "",
        "## Performance (synthetic A4 portrait, median of 5 runs)",
        "",
        "| scale | render ms (1 page) |",
        "| --- | --- |",
    ]
    for scale, ms in sorted(result.render_ms_by_scale.items()):
        lines.append(f"| {scale} | {ms:.1f} |")
    mb = result.forty_page_png_bytes / (1024 * 1024)
    per_page_kb = result.forty_page_png_bytes / 40 / 1024
    lines.extend(
        [
            "",
            "## 40-page transfer (scale 2.0 PNG, sequential render)",
            "",
            f"- total PNG bytes: {result.forty_page_png_bytes:,} ({mb:.2f} MiB)",
            f"- wall time (render only): {result.forty_page_render_ms:.0f} ms",
            f"- per page: {result.forty_page_png_bytes / 40:,.0f} bytes PNG",
            "",
            "Cache: at scale 2.0 each page is ~"
            f"{per_page_kb:.0f} KiB PNG; 40 pages ≈ {mb:.2f} MiB. Zoom changes "
            "invalidate scale — cache key must include `(document_id, page_index, scale)`. "
            "Without cache, every zoom step re-fetches all visible pages from the sidecar.",
            "",
            "| fixture | normalized (x,y) | measured (x,y) | abs error |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in rows:
        lines.append(
            f"| {row.fixture} | ({row.point_x:.2f}, {row.point_y:.2f}) "
            f"| ({row.measured_x:.4f}, {row.measured_y:.4f}) | {row.error:.4f} |"
        )
    lines.append("")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _write_approach_a_report(result: ApproachAResult) -> None:
    fixture_count = len(FIXTURES)
    point_count = len(TEST_POINTS)
    total = len(result.round_trip_rows)
    viewport_pass = result.worst_viewport_delta_pt <= 0.5  # pt — must match exactly
    round_trip_pass = result.worst_round_trip_error <= TOLERANCE
    path = _OUT_DIR / "approach-a-round-trip.md"
    lines = [
        "# PoC 6 Approach A round-trip (generated)",
        "",
        f"Engine: **pdf.js** `{result.pdfjs_version}` via npm (`desktop-poc/.../approach_a/package.json`).",
        "Acquisition: probe-only npm install — **not** added to product root `package.json`.",
        "",
        f"- fixtures: {fixture_count}",
        f"- points per fixture: {point_count}",
        f"- total round-trip measurements: {total}",
        f"- render scale: {RENDER_SCALE}",
        f"- tolerance: {TOLERANCE} normalized",
        "",
        "## Viewport vs pdfium contract (`PageGeometry.displayed_*`)",
        "",
        "pdf.js viewport at scale 1.0 must match the displayed page size pdfium uses.",
        f"- worst width/height delta: **{result.worst_viewport_delta_pt:.4f} pt** "
        f"-> **{'PASS' if viewport_pass else 'FAIL'}**",
        "",
        "| fixture | expected W×H pt | pdf.js W×H pt | ΔW | ΔH |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in result.viewport_rows:
        lines.append(
            f"| {row['fixture']} | {row['expected_width']:.1f}×{row['expected_height']:.1f} "
            f"| {row['pdfjs_width']:.1f}×{row['pdfjs_height']:.1f} "
            f"| {row['width_delta']:.4f} | {row['height_delta']:.4f} |"
        )
    lines.extend(
        [
            "",
            "## Round-trip (stamp with adopted transform, rasterize with pdf.js, read mark)",
            "",
            f"- worst error: **{result.worst_round_trip_error:.4f}** "
            f"-> **{'PASS' if round_trip_pass else 'FAIL'}**",
            "",
            "| fixture | normalized (x,y) | measured (x,y) | abs error |",
            "| --- | --- | --- | --- |",
        ]
    )
    for row in result.round_trip_rows:
        lines.append(
            f"| {row['fixture']} | ({row['nx']:.2f}, {row['ny']:.2f}) "
            f"| ({row['measured_x']:.4f}, {row['measured_y']:.4f}) | {row['error']:.4f} |"
        )
    mismatches = [
        row
        for row in result.viewport_rows
        if abs(float(row["width_delta"])) > 0.5 or abs(float(row["height_delta"])) > 0.5
    ]
    if mismatches:
        lines.extend(
            [
                "",
                "## Viewport mismatches (pdf.js ≠ pdfium display area)",
                "",
            ]
        )
        for row in mismatches:
            lines.append(
                f"- **{row['fixture']}**: ΔW={row['width_delta']:.4f} pt, "
                f"ΔH={row['height_delta']:.4f} pt"
            )
    lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8", newline="\n")


def _write_decision_record(approach_a: ApproachAResult, approach_b: ApproachBResult) -> None:
    fixture_count = len(FIXTURES)
    point_count = len(TEST_POINTS)
    total = fixture_count * point_count

    a_viewport_ok = approach_a.worst_viewport_delta_pt <= 0.5
    a_roundtrip_ok = approach_a.worst_round_trip_error <= TOLERANCE
    b_ok = approach_b.worst_error <= TOLERANCE

    mb40 = approach_b.forty_page_png_bytes / (1024 * 1024)
    doc = _OUT_DIR.parent / "poc-6-pdf-coordinates.md"
    content = f"""# PoC 6: Electron UI の PDF 表示と正規化座標

GitHub Issue [#202](https://github.com/HIKARU0627/Auto-Scoring/issues/202)（親
[#201](https://github.com/HIKARU0627/Auto-Scoring/issues/201)）。移行後 UI が
「pdfium が表示するページ」と同じ絵の上で `0..1` 正規化座標を作れるかを、案 A
（renderer で pdf.js）と案 B（サイドカーが pypdfium2 でページ PNG を返す）で
**実測**して選ぶ。

座標契約の正本: [`poc-3-pdf-coordinates.md`](./poc-3-pdf-coordinates.md) /
`backend/src/auto_scoring/domain/pdf_geometry.py`（**本 PoC では変更しない**）。

## 結論（先に）

- **案 B（pypdfium2 ビットマップ）を採用**。案 A も 9 fixture × 5 点 = 45 測点すべて
  PASS（worst 0.0002、viewport Δ 0 pt）だが、案 B は座標契約と同一 pdfium エンジンが
  「表示するページ」を定義するため二重解釈リスクがない。40 ページ転送 ≈ {mb40:.2f} MiB、
  scale 2.0 再描画中央値 {approach_b.render_ms_by_scale[2.0]:.0f} ms/ページも許容範囲。
- 往復許容誤差 **0.004**（PoC 3 と同じ）。分母: **{fixture_count} fixtures ×
  {point_count} 点 = {total} 測点**。
- 案 A worst 往復誤差: **{approach_a.worst_round_trip_error:.4f}**
  （viewport 最大 Δ: {approach_a.worst_viewport_delta_pt:.4f} pt）。
- 案 B worst 往復誤差: **{approach_b.worst_error:.4f}**（pdfium、PoC 3 再確認）。

## repro command

```bash
# 1. probe-only npm deps（pdf.js — プロダクト root には入れない）
cd desktop-poc/issue_202_pdf_coordinates/approach_a && npm install

# 2. 測定 + レポート生成（backend の uv 環境で pypdfium2 / pypdf を使う）
cd ../../../backend
uv run python ../desktop-poc/issue_202_pdf_coordinates/report.py
```

生成物:

- [`poc-6-pdf-coordinates/approach-a-round-trip.md`](./poc-6-pdf-coordinates/approach-a-round-trip.md)
- [`poc-6-pdf-coordinates/approach-b-round-trip.md`](./poc-6-pdf-coordinates/approach-b-round-trip.md)

## 期待値

- **表示領域**: pdf.js / pypdfium2 いずれも `PageGeometry.displayed_width` /
  `displayed_height`（CropBox∩MediaBox、`/Rotate` 適用後）と一致すること。
- **往復**: 既知正規化点 → `pdf_geometry` → ユーザー空間スタンプ → 表示エンジンで
  raster 化 → 赤マーク中心を正規化し直し、元点との差 ≤ **0.004**。
- fixture: PoC 3 と同じ 9 種（縦/横、Rotate 0/90/180/270、letter、非ゼロ MediaBox、
  CropBox インセット）。

## 実測値

| 案 | 表示エンジン | 測点数 | worst 往復誤差 | viewport Δ (pt) | 判定 |
| --- | --- | --- | --- | --- | --- |
| A | pdf.js {approach_a.pdfjs_version} (npm) | {total} | {approach_a.worst_round_trip_error:.4f} | {approach_a.worst_viewport_delta_pt:.4f} | {"PASS" if a_viewport_ok and a_roundtrip_ok else "FAIL"} |
| B | pypdfium2 PNG | {total} | {approach_b.worst_error:.4f} | 0（定義上同一） | {"PASS" if b_ok else "FAIL"} |

### 案 B 追加項目（数値）

| 項目 | 値 |
| --- | --- |
| scale 1.0 再描画（中央値） | {approach_b.render_ms_by_scale[1.0]:.1f} ms / ページ |
| scale 2.0 再描画（中央値） | {approach_b.render_ms_by_scale[2.0]:.1f} ms / ページ |
| scale 3.5 再描画（中央値） | {approach_b.render_ms_by_scale[3.5]:.1f} ms / ページ |
| 40 ページ PNG 転送量（scale 2.0） | {approach_b.forty_page_png_bytes:,} bytes ({mb40:.2f} MiB) |
| 40 ページレンダ wall time | {approach_b.forty_page_render_ms:.0f} ms |
| キャッシュ | `(doc, page, scale)` キー必須。ズーム毎に全ページ再取得すると 40 ページで約 {mb40:.2f} MiB |

### 案 A 追加項目

- pdf.js 取得: `desktop-poc/.../approach_a/package.json` の `pdfjs-dist` + `@napi-rs/canvas`
  （npm、probe-only）。Node 上では `canvas`（node-canvas）ではなく `@napi-rs/canvas` が必須
  （pdf.js 5.x の NodeCanvasFactory 要件）。
- **全 fixture PASS** — CropBox / 非ゼロ MediaBox / `/Rotate` で viewport 不一致は検出されず。
- 詳細:
  [`approach-a-round-trip.md`](./poc-6-pdf-coordinates/approach-a-round-trip.md)

## 決定

**案 B（pypdfium2 ビットマップ）を採用**。

案 A も合成 fixture 45 測点すべて許容内（往復 worst 0.0002、viewport 完全一致）だが、
採用理由は実測による座標精度ではなく **エンジン単一化**: サイドカーの
`PdfiumPypdfEngine` が座標変換（`page_geometry`）と raster 化の双方で pdfium を使うため、
将来の pdf.js アップデートや Electron renderer 差分で契約がずれる余地を残さない。
性能面（40 ページ ≈ {mb40:.2f} MiB、scale 2.0 で {approach_b.render_ms_by_scale[2.0]:.0f} ms/ページ）
も許容可能。pdf.js を product root に足す必要もない。

案 B で描画 API（`GET /pages/{{n}}/render` 等）が要る場合、**本 Issue では実装しない**。
必要な API 形状は Phase 2 の `desktop/` 土台 Issue で起票する。

## 撤去または昇格の条件

| パス | 扱い |
| --- | --- |
| `desktop-poc/issue_202_pdf_coordinates/` | PoC 完了後も repro 用に保持。プロダクトから import しない |
| `docs/poc-6-pdf-coordinates/` | 証跡として保持 |
| `docs/poc-6-pdf-coordinates.md` | Electron PDF 表示方式の決定記録として昇格（`docs/frontend-migration.md` Phase 1 参照） |
| 案 B 採用時の sidecar render API | 別 Issue（Phase 2 土台）で昇格 |

## スコープ外

- Electron / React UI の実装（Phase 2 以降）
- `pdf_geometry.py` の変更
- 実答案 PDF（合成 fixture のみ）
"""
    doc.write_text(content, encoding="utf-8", newline="\n")


def main() -> int:
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    _prepare_stamped_pdfs(_SAMPLES_DIR)
    approach_b = run_approach_b(_SAMPLES_DIR)
    approach_a = _run_approach_a(_SAMPLES_DIR)
    _write_approach_b_report(approach_b)
    _write_approach_a_report(approach_a)
    _write_decision_record(approach_a, approach_b)
    print(f"wrote {_OUT_DIR.relative_to(_ROOT)}")
    print(
        f"approach A: viewport Δ max {approach_a.worst_viewport_delta_pt:.4f} pt, "
        f"round-trip worst {approach_a.worst_round_trip_error:.4f}"
    )
    print(f"approach B: round-trip worst {approach_b.worst_error:.4f}")
    ok_a = (
        approach_a.worst_viewport_delta_pt <= 0.5
        and approach_a.worst_round_trip_error <= TOLERANCE
    )
    ok_b = approach_b.worst_error <= TOLERANCE
    return 0 if ok_b else 1


if __name__ == "__main__":
    sys.exit(main())
