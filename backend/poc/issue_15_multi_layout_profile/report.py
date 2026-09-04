"""PoC 4 (issue #15) repro command: regenerate the round-trip report and samples.

    uv run python poc/issue_15_multi_layout_profile/report.py

Builds the same fixtures as `backend/tests/test_profile_round_trip.py` (the
authoritative pass/fail check), runs candidate generation -> save (DRAFT) ->
reload -> a simulated human correction -> confirm -> save (CONFIRMED) ->
reload -> reapply to five jittered student copies per format, and writes:

* ``docs/poc-4-multi-layout-profiles/samples/<format>.model.pdf``   -- source
* ``docs/poc-4-multi-layout-profiles/samples/<format>.grading-manual.pdf``
* ``docs/poc-4-multi-layout-profiles/samples/<format>.student-N.pdf``
* ``docs/poc-4-multi-layout-profiles/app-data/tests/<format>/profile.json``
  -- the saved profile (Issue #11's storage layout; see
  `auto_scoring.adapters.local.ProfileStore`), left as the last-written
  (CONFIRMED) content
* ``docs/poc-4-multi-layout-profiles/round-trip-report.md``         -- table

One fixture (format E) stores its page as A4 MediaBox with `/Rotate 90` and a
CropBox inset, exercising `PageGeometry` rotation/crop handling (PoC 3 /
Issue #12's adopted `PdfEngine` contract) rather than plain page width/height.

Exits non-zero if any reapplied region drifts beyond tolerance, or if the
hard-to-detect fixture's manual fallback misbehaves. Deterministic: re-running
reproduces byte-identical numbers (`app-data/` JSON included).
"""

from __future__ import annotations

import sys
from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

from pypdf import PdfWriter
from pypdf.annotations import Rectangle
from pypdf.generic import NameObject, NumberObject, RectangleObject, TextStringObject

from auto_scoring.adapters.local import ProfileStore
from auto_scoring.adapters.pdf import read_markers
from auto_scoring.domain.profile import NormalizedBBox, PageFormat, Profile, Region, RegionKind
from auto_scoring.domain.profile_apply import reapply_profile
from auto_scoring.domain.profile_detection import (
    RectPt,
    generate_candidates,
    requires_manual_fallback,
    unrecognized_tags,
)

_BBOX_TOLERANCE = 0.01
_OUT_DIR = Path(__file__).resolve().parents[3] / "docs" / "poc-4-multi-layout-profiles"
_SAMPLES_DIR = _OUT_DIR / "samples"

AnnotationSpec = tuple[int, str, RectPt]
_MODEL_ONLY_TAGS = ("SCORE", "RUBRIC", "MODEL_ANSWER")
_GRADING_MANUAL_TAGS = ("SCORE", "RUBRIC")


@dataclass(frozen=True)
class PageSpec:
    """A page to build for a fixture PDF: MediaBox size plus optional `/Rotate` and `CropBox`."""

    media_width: float
    media_height: float
    rotation: int = 0
    crop: tuple[float, float, float, float] | None = None  # (left, bottom, right, top)


@dataclass(frozen=True)
class FixtureFormat:
    format_id: str
    description: str
    pages: tuple[PageSpec, ...]
    model_annotations: tuple[AnnotationSpec, ...]


_A4_PORTRAIT = PageFormat(595.0, 842.0)  # plain PageFormat, for the freeform-fallback fixture
_A4_PORTRAIT_SPEC = PageSpec(595.0, 842.0)
_A4_LANDSCAPE_SPEC = PageSpec(842.0, 595.0)
_B5_PORTRAIT_SPEC = PageSpec(498.0, 709.0)

FORMAT_A = FixtureFormat(
    "format-a-single-page-stacked",
    "1 page / portrait / 2 questions stacked vertically / short boxed answer areas",
    (_A4_PORTRAIT_SPEC,),
    (
        (0, "Q1", (72, 760, 523, 790)),
        (0, "ANSWER_1", (72, 650, 450, 755)),
        (0, "Q2", (72, 560, 523, 590)),
        (0, "ANSWER_2", (72, 450, 450, 555)),
        (0, "ANNOT", (460, 400, 565, 800)),
        (0, "SCORE", (460, 780, 565, 800)),
        (0, "RUBRIC", (72, 300, 523, 430)),
        (0, "MODEL_ANSWER", (72, 150, 523, 290)),
    ),
)

FORMAT_B = FixtureFormat(
    "format-b-two-page-landscape-2col",
    "2 pages / landscape / 2-column questions / large free-form answer areas",
    (_A4_LANDSCAPE_SPEC, _A4_LANDSCAPE_SPEC),
    (
        (0, "Q1", (40, 500, 400, 560)),
        (0, "ANSWER_1", (40, 120, 400, 490)),
        (0, "Q2", (440, 500, 800, 560)),
        (0, "ANSWER_2", (440, 120, 800, 490)),
        (0, "ANNOT", (40, 20, 800, 90)),
        (1, "Q3", (40, 520, 400, 560)),
        (1, "ANSWER_3", (40, 300, 400, 510)),
        (1, "RUBRIC", (40, 120, 400, 290)),
        (1, "SCORE", (440, 520, 800, 560)),
        (1, "MODEL_ANSWER", (440, 120, 800, 510)),
        (1, "ANNOT", (40, 20, 800, 90)),
    ),
)

FORMAT_C = FixtureFormat(
    "format-c-three-page-mixed-split-answers",
    (
        "3 pages / mixed sizes+orientation (A4 portrait, A4 landscape, B5 portrait) / "
        "1 sparse question per page / multi-part split answer boxes"
    ),
    (_A4_PORTRAIT_SPEC, _A4_LANDSCAPE_SPEC, _B5_PORTRAIT_SPEC),
    (
        (0, "Q1", (72, 700, 523, 760)),
        (0, "ANSWER_1", (72, 600, 290, 690)),
        (0, "ANSWER_2", (305, 600, 523, 690)),
        (0, "ANNOT", (72, 500, 523, 560)),
        (0, "SCORE", (72, 420, 523, 480)),
        (0, "RUBRIC", (72, 300, 523, 400)),
        (0, "MODEL_ANSWER", (72, 150, 523, 280)),
        (1, "Q2", (40, 500, 800, 560)),
        (1, "ANSWER_3", (40, 300, 260, 480)),
        (1, "ANSWER_4", (291, 300, 511, 480)),
        (1, "ANSWER_5", (542, 300, 800, 480)),
        (1, "ANNOT", (40, 120, 800, 270)),
        (2, "Q3", (40, 620, 458, 670)),
        (2, "ANSWER_6", (40, 300, 458, 600)),
        (2, "ANNOT", (40, 120, 458, 270)),
    ),
)

FORMAT_D = FixtureFormat(
    "format-d-single-page-2x2-grid",
    "1 page / portrait / 4 questions in a 2x2 grid / grid-cell answer areas / "
    "one small annotation strip per question instead of a shared margin",
    (_A4_PORTRAIT_SPEC,),
    (
        (0, "Q1", (40, 760, 280, 790)),
        (0, "ANSWER_1", (40, 660, 280, 745)),
        (0, "ANNOT_1", (40, 635, 280, 655)),
        (0, "Q2", (315, 760, 555, 790)),
        (0, "ANSWER_2", (315, 660, 555, 745)),
        (0, "ANNOT_2", (315, 635, 555, 655)),
        (0, "Q3", (40, 560, 280, 590)),
        (0, "ANSWER_3", (40, 460, 280, 545)),
        (0, "ANNOT_3", (40, 435, 280, 455)),
        (0, "Q4", (315, 560, 555, 590)),
        (0, "ANSWER_4", (315, 460, 555, 545)),
        (0, "ANNOT_4", (315, 435, 555, 455)),
        (0, "SCORE", (40, 380, 555, 420)),
        (0, "RUBRIC", (40, 260, 555, 370)),
        (0, "MODEL_ANSWER", (40, 100, 555, 250)),
    ),
)

# A4 MediaBox, /Rotate 90 (displays landscape although stored portrait), and a
# CropBox inset -- exercises the PageGeometry rotation + crop-offset path the
# other formats never touch (their pages are unrotated with CropBox == MediaBox).
FORMAT_E = FixtureFormat(
    "format-e-rotated-cropbox",
    "1 page / A4 MediaBox with /Rotate 90 + CropBox inset (displays landscape) / "
    "single question / exercises PageGeometry rotation and crop-offset handling",
    (PageSpec(595.0, 842.0, rotation=90, crop=(30.0, 40.0, 565.0, 800.0)),),
    (
        (0, "Q1", (60, 700, 500, 760)),
        (0, "ANSWER_1", (60, 500, 500, 690)),
        (0, "ANNOT", (60, 450, 500, 490)),
        (0, "SCORE", (60, 400, 500, 440)),
        (0, "RUBRIC", (60, 200, 500, 390)),
        (0, "MODEL_ANSWER", (60, 60, 500, 190)),
    ),
)

# docs/business-rules-and-evaluation-data.md §6.2: >=4 formats x >=5 answers each;
# E is an extra fixture for rotation/CropBox coverage specifically.
FORMATS = (FORMAT_A, FORMAT_B, FORMAT_C, FORMAT_D, FORMAT_E)
_JITTERS = ((0.4, -0.3), (-0.4, 0.3), (0.3, 0.4), (-0.3, -0.4), (0.2, -0.2))


def _write_pdf(
    path: Path, pages: Sequence[PageSpec], annotations: Sequence[AnnotationSpec]
) -> None:
    writer = PdfWriter()
    for page in pages:
        writer.add_blank_page(width=page.media_width, height=page.media_height)
    for index, page in enumerate(pages):
        if page.rotation:
            writer.pages[index][NameObject("/Rotate")] = NumberObject(page.rotation)
        if page.crop is not None:
            writer.pages[index][NameObject("/CropBox")] = RectangleObject(list(page.crop))
    for page_index, tag, rect in annotations:
        annotation = Rectangle(rect=rect)
        annotation[NameObject("/Contents")] = TextStringObject(tag)
        writer.add_annotation(page_number=page_index, annotation=annotation)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        writer.write(handle)


def _jitter(annotations: Sequence[AnnotationSpec], dx: float, dy: float) -> list[AnnotationSpec]:
    return [
        (page, tag, (x0 + dx, y0 + dy, x1 + dx, y1 + dy))
        for page, tag, (x0, y0, x1, y1) in annotations
    ]


def _student_markers(annotations: Sequence[AnnotationSpec]) -> list[AnnotationSpec]:
    return [item for item in annotations if item[1] not in _MODEL_ONLY_TAGS]


def _model_answer_markers(annotations: Sequence[AnnotationSpec]) -> list[AnnotationSpec]:
    return [item for item in annotations if item[1] not in _GRADING_MANUAL_TAGS]


def _grading_manual_markers(annotations: Sequence[AnnotationSpec]) -> list[AnnotationSpec]:
    return [item for item in annotations if item[1] in _GRADING_MANUAL_TAGS]


def _shrink(bbox: NormalizedBBox, delta: float) -> tuple[float, float, float, float]:
    return (bbox.x0, bbox.y0, bbox.x1 - delta, bbox.y1)


def run_format(fixture: FixtureFormat, store: ProfileStore, rows: list[str]) -> bool:
    model_path = _SAMPLES_DIR / f"{fixture.format_id}.model.pdf"
    manual_path = _SAMPLES_DIR / f"{fixture.format_id}.grading-manual.pdf"
    _write_pdf(model_path, fixture.pages, _model_answer_markers(fixture.model_annotations))
    _write_pdf(manual_path, fixture.pages, _grading_manual_markers(fixture.model_annotations))

    markers, signature, page_geometries = read_markers(model_path)
    manual_markers, manual_signature, _ = read_markers(manual_path)
    if not signature.matches(manual_signature):
        return False
    markers.extend(manual_markers)
    draft = generate_candidates("profile-1", fixture.format_id, signature, page_geometries, markers)

    # Save the DRAFT, then reload it before review -- see docstring.
    store.save(draft)
    reloaded_draft = store.load(fixture.format_id)

    corrected_region_id = reloaded_draft.regions[0].region_id
    corrected_bbox = NormalizedBBox(*_shrink(reloaded_draft.regions[0].bbox, 0.01))
    reviewed = [
        replace(region, bbox=corrected_bbox, confirmed=True)
        if region.region_id == corrected_region_id
        else replace(region, confirmed=True)
        for region in reloaded_draft.regions
    ]
    confirmed = reloaded_draft.confirm(reviewed)
    store.save(confirmed)  # overwrites the DRAFT profile.json in place

    student_annotations = _student_markers(fixture.model_annotations)
    ok = True
    for copy_index, (dx, dy) in enumerate(_JITTERS):
        student_path = _SAMPLES_DIR / f"{fixture.format_id}.student-{copy_index}.pdf"
        _write_pdf(student_path, fixture.pages, _jitter(student_annotations, dx, dy))

        student_markers, student_signature, student_geometries = read_markers(student_path)
        # Reload for every student copy: reapply acts on a fresh deserialize
        # of profile.json, not the in-memory `confirmed` object.
        profile_for_reapply = store.load(fixture.format_id)
        applied = reapply_profile(profile_for_reapply, fixture.format_id, student_signature)
        ground_truth = generate_candidates(
            "ground-truth",
            fixture.format_id,
            student_signature,
            student_geometries,
            student_markers,
        ).regions
        ground_truth_by_key = {(r.page_index, r.label): r for r in ground_truth}

        for region in applied.regions:
            key = (region.page_index, region.label)
            if region.region_id == corrected_region_id:
                distance = region.bbox.max_corner_distance(corrected_bbox)
                note = "human correction persisted"
            elif key in ground_truth_by_key:
                distance = region.bbox.max_corner_distance(ground_truth_by_key[key].bbox)
                note = "vs. student sheet's own marker"
            else:
                distance = 0.0
                note = "profile-only (not printed on student sheet)"
            verdict = "PASS" if distance <= _BBOX_TOLERANCE else "FAIL"
            ok = ok and verdict == "PASS"
            rows.append(
                f"| {fixture.format_id} | student-{copy_index} | {region.label} "
                f"| p{region.page_index} | {distance:.4f} | {verdict} | {note} |"
            )
    return ok


def run_hard_to_detect_fixture(store: ProfileStore, rows: list[str]) -> bool:
    pages = (_A4_PORTRAIT_SPEC,)
    freeform_annotation: tuple[AnnotationSpec, ...] = ((0, "NOTES", (40, 40, 555, 800)),)
    model_path = _SAMPLES_DIR / "format-freeform-essay.model.pdf"
    _write_pdf(model_path, pages, freeform_annotation)
    markers, signature, page_geometries = read_markers(model_path)

    tags = unrecognized_tags(markers)
    auto_profile = generate_candidates(
        "profile-freeform", "format-freeform-essay", signature, page_geometries, markers
    )
    detection_failed = tags == ["NOTES"] and auto_profile.regions == ()

    manual_regions = (
        Region(
            "manual-q1",
            RegionKind.QUESTION,
            0,
            NormalizedBBox(0.07, 0.05, 0.93, 0.12),
            "manual:question",
        ),
        Region(
            "manual-answer",
            RegionKind.ANSWER_AREA,
            0,
            NormalizedBBox(0.07, 0.13, 0.93, 0.95),
            "manual:answer_area",
        ),
    )
    manual_draft = Profile.from_candidates(
        "profile-freeform", "format-freeform-essay", signature, manual_regions
    )
    confirmed = manual_draft.confirm(
        [replace(region, confirmed=True) for region in manual_draft.regions]
    )
    store.save(confirmed)
    reloaded = store.load("format-freeform-essay")

    student_path = _SAMPLES_DIR / "format-freeform-essay.student-0.pdf"
    _write_pdf(student_path, pages, freeform_annotation)
    _, student_signature, _ = read_markers(student_path)
    applied = reapply_profile(reloaded, "format-freeform-essay", student_signature)
    fallback_ok = requires_manual_fallback(markers, auto_profile) and len(applied.regions) == 2

    verdict = "PASS" if detection_failed and fallback_ok else "FAIL"
    unrecognized_ok = tags == ["NOTES"]
    zero_candidates = auto_profile.regions == ()
    rows.append(
        f"| format-freeform-essay | (manual fallback) | unrecognized tag: {unrecognized_ok}; "
        f"0 auto candidates: {zero_candidates}; manual profile reapplies: {fallback_ok} "
        f"| -- | -- | {verdict} | manual fallback path |"
    )
    return verdict == "PASS"


def main() -> int:
    rows: list[str] = []
    ok = True
    store = ProfileStore(_OUT_DIR / "app-data")
    for fixture in FORMATS:
        ok = run_format(fixture, store, rows) and ok
    ok = run_hard_to_detect_fixture(store, rows) and ok

    header = (
        "| format | student copy | region | page | drift (normalized) | verdict | note |\n"
        "| --- | --- | --- | --- | --- | --- | --- |\n"
    )
    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    report_path = _OUT_DIR / "round-trip-report.md"
    report_path.write_text(
        "# PoC 4 round-trip report\n\n"
        f"Tolerance: {_BBOX_TOLERANCE} normalized units. Regenerate with "
        "`uv run python poc/issue_15_multi_layout_profile/report.py`.\n\n"
        + header
        + "\n".join(rows)
        + "\n",
        encoding="utf-8",
    )
    print(f"wrote {report_path}")
    print(f"wrote samples to {_SAMPLES_DIR}")
    print("PASS" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
