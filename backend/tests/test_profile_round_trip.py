"""PoC 4 (Issue #15) repro command: profile generation -> human confirm -> reapply.

    uv run pytest tests/test_profile_round_trip.py

Four fixture *formats* (A/B/C/D below) vary page count, orientation, question
layout, and answer-area shape -- the dimensions Issue #15 asks to cover, and
match the >=4 formats x >=5 answers evaluation-data target in
`docs/business-rules-and-evaluation-data.md` §6.2. For each format:

1. A "model answer" PDF carries all six marker kinds (question, answer area,
   annotation area, score, rubric, model answer) as tagged PDF annotations --
   this PoC's stand-in for a real text/vision extraction layer (see
   `auto_scoring.domain.profile_detection`).
2. `generate_candidates` turns those markers into an unconfirmed (DRAFT)
   profile. A simulated human correction nudges one region and confirms the
   rest, producing the CONFIRMED profile that alone may be reapplied.
3. Five "student answer" PDFs of the *same format* carry only the
   question/answer-area/annotation-area markers (a blank answer sheet has no
   printed score/rubric/model-answer), each with a small positional jitter
   (print/scan tolerance). `reapply_profile` binds the confirmed profile to
   each student document; the reapplied question/answer/annotation regions
   are checked against that document's own markers within tolerance, and the
   score/rubric/model-answer regions -- which the student sheet cannot
   supply -- are checked to still be present, verbatim from the profile.

A fifth, separate fixture (a free-form essay sheet with no recognizable
markers at all) exercises the manual-fallback path instead of the round trip.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.annotations import Rectangle
from pypdf.generic import NameObject, TextStringObject

from auto_scoring.adapters.pdf import read_markers
from auto_scoring.domain.profile import NormalizedBBox, PageFormat, Profile, Region, RegionKind
from auto_scoring.domain.profile_apply import FormatMismatchError, reapply_profile
from auto_scoring.domain.profile_detection import (
    RectPt,
    generate_candidates,
    unrecognized_tags,
)

# Normalized-bbox tolerance for "did the reapplied region land on the right
# content": jitter below is <=0.4pt against pages 498-842pt wide/tall, i.e.
# <=0.0008 normalized. 0.01 leaves ample margin while still catching an
# axis mix-up (which would be off by ~0.5).
_BBOX_TOLERANCE = 0.01

# 5 answer sheets per format, simulating small print/scan positional variance
# (docs/business-rules-and-evaluation-data.md §6.2: >=5 answers per format).
_STUDENT_JITTERS = ((0.4, -0.3), (-0.4, 0.3), (0.3, 0.4), (-0.3, -0.4), (0.2, -0.2))

AnnotationSpec = tuple[int, str, RectPt]  # (page_index, tag, rect_pt)


def _write_pdf(
    path: Path, pages: Sequence[PageFormat], annotations: Sequence[AnnotationSpec]
) -> None:
    writer = PdfWriter()
    for page in pages:
        writer.add_blank_page(width=page.width_pt, height=page.height_pt)
    for page_index, tag, rect in annotations:
        annotation = Rectangle(rect=rect)
        annotation[NameObject("/Contents")] = TextStringObject(tag)
        writer.add_annotation(page_number=page_index, annotation=annotation)
    with path.open("wb") as handle:
        writer.write(handle)


def _jitter(annotations: Sequence[AnnotationSpec], dx: float, dy: float) -> list[AnnotationSpec]:
    return [
        (page, tag, (x0 + dx, y0 + dy, x1 + dx, y1 + dy))
        for page, tag, (x0, y0, x1, y1) in annotations
    ]


# Marker kinds a printed answer sheet cannot carry: they only exist on the
# model-answer / grading-manual PDF the profile was generated from.
_MODEL_ONLY_TAGS = ("SCORE", "RUBRIC", "MODEL_ANSWER")


def _student_markers(annotations: Sequence[AnnotationSpec]) -> list[AnnotationSpec]:
    return [item for item in annotations if item[1] not in _MODEL_ONLY_TAGS]


@dataclass(frozen=True)
class FixtureFormat:
    format_id: str
    description: str
    pages: tuple[PageFormat, ...]
    model_annotations: tuple[AnnotationSpec, ...]


_A4_PORTRAIT = PageFormat(595.0, 842.0)
_A4_LANDSCAPE = PageFormat(842.0, 595.0)
_B5_PORTRAIT = PageFormat(498.0, 709.0)

FORMAT_A = FixtureFormat(
    format_id="format-a-single-page-stacked",
    description="1 page / portrait / 2 questions stacked vertically / short boxed answer areas",
    pages=(_A4_PORTRAIT,),
    model_annotations=(
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
    format_id="format-b-two-page-landscape-2col",
    description="2 pages / landscape / 2-column questions / large free-form answer areas",
    pages=(_A4_LANDSCAPE, _A4_LANDSCAPE),
    model_annotations=(
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
    format_id="format-c-three-page-mixed-split-answers",
    description=(
        "3 pages / mixed sizes+orientation (A4 portrait, A4 landscape, B5 portrait) / "
        "1 sparse question per page / multi-part split answer boxes"
    ),
    pages=(_A4_PORTRAIT, _A4_LANDSCAPE, _B5_PORTRAIT),
    model_annotations=(
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
    format_id="format-d-single-page-2x2-grid",
    description=(
        "1 page / portrait / 4 questions in a 2x2 grid / grid-cell answer areas / "
        "one small annotation strip per question instead of a shared margin"
    ),
    pages=(_A4_PORTRAIT,),
    model_annotations=(
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

# The evaluation-data decision (docs/business-rules-and-evaluation-data.md §6.2)
# targets 4 formats x >=5 answer sheets each for PoC 4.
FORMATS = (FORMAT_A, FORMAT_B, FORMAT_C, FORMAT_D)


@pytest.mark.parametrize("fixture", FORMATS, ids=lambda f: f.format_id)
def test_profile_round_trip_reapplies_within_tolerance(
    fixture: FixtureFormat, tmp_path: Path
) -> None:
    model_path = tmp_path / "model.pdf"
    _write_pdf(model_path, fixture.pages, fixture.model_annotations)

    markers, signature = read_markers(model_path)
    assert not unrecognized_tags(markers), "fixture uses only tags this PoC's detector recognizes"

    draft = generate_candidates("profile-1", fixture.format_id, signature, markers)
    # every candidate must start unconfirmed, whatever the marker says
    assert all(not region.confirmed for region in draft.regions)
    assert len(draft.regions) == len(fixture.model_annotations)

    # Simulate a human correction: nudge the first question's right edge, then confirm everything.
    # The correction is deliberately larger than _BBOX_TOLERANCE and must persist verbatim through
    # reapply -- it is excluded from the ground-truth comparison below for that reason.
    corrected_region_id = draft.regions[0].region_id
    corrected_bbox = NormalizedBBox(*_shrink(draft.regions[0].bbox, 0.01))
    reviewed = []
    for index, region in enumerate(draft.regions):
        if index == 0:
            region = replace(region, bbox=corrected_bbox)
        reviewed.append(replace(region, confirmed=True))
    confirmed = draft.confirm(reviewed)

    student_annotations = _student_markers(fixture.model_annotations)
    for copy_index, (dx, dy) in enumerate(_STUDENT_JITTERS):
        student_path = tmp_path / f"student-{copy_index}.pdf"
        _write_pdf(student_path, fixture.pages, _jitter(student_annotations, dx, dy))

        student_markers, student_signature = read_markers(student_path)
        applied = reapply_profile(
            confirmed, f"{fixture.format_id}-student-{copy_index}", student_signature
        )
        assert len(applied.regions) == len(confirmed.regions), "reapply must not drop any region"

        ground_truth = generate_candidates(
            "ground-truth", fixture.format_id, student_signature, student_markers
        ).regions
        # tags such as "ANNOT" repeat across pages, so key ground truth by
        # (page, tag) rather than tag alone.
        ground_truth_by_key = {(region.page_index, region.label): region for region in ground_truth}

        for region in applied.regions:
            key = (region.page_index, region.label)
            if region.region_id == corrected_region_id:
                # the human correction must survive reapply unchanged, not get
                # overwritten by re-detecting the (uncorrected) printed marker.
                assert region.bbox == corrected_bbox
            elif key in ground_truth_by_key:
                truth = ground_truth_by_key[key]
                distance = region.bbox.max_corner_distance(truth.bbox)
                assert distance <= _BBOX_TOLERANCE, (
                    f"{fixture.format_id}/{region.label}: reapplied bbox drifted "
                    f"{distance:.4f} from the student sheet's own markers"
                )
            else:
                # score/rubric/model_answer: the student sheet has none of these
                # printed -- the profile is the only source for them.
                assert region.label in _MODEL_ONLY_TAGS


def test_reapply_rejects_mismatched_format(tmp_path: Path) -> None:
    a_path = tmp_path / "format-a.pdf"
    _write_pdf(a_path, FORMAT_A.pages, FORMAT_A.model_annotations)
    a_markers, a_signature = read_markers(a_path)
    a_profile = generate_candidates("profile-a", FORMAT_A.format_id, a_signature, a_markers)
    a_reviewed = [replace(region, confirmed=True) for region in a_profile.regions]
    a_confirmed = a_profile.confirm(a_reviewed)

    b_path = tmp_path / "format-b.pdf"
    _write_pdf(b_path, FORMAT_B.pages, FORMAT_B.model_annotations)
    _, b_signature = read_markers(b_path)

    with pytest.raises(FormatMismatchError):
        reapply_profile(a_confirmed, FORMAT_B.format_id, b_signature)


def test_hard_to_detect_format_falls_back_to_manual_region(tmp_path: Path) -> None:
    """A free-form essay sheet has no recognizable markers at all.

    Detection condition for "give up and ask a human": `unrecognized_tags`
    is non-empty and/or no QUESTION/ANSWER_AREA candidate was produced.
    Manual fallback: a human supplies the missing regions directly (not from
    detection) and confirms them; the resulting profile still reapplies to
    other documents of the same (page-size) format normally.
    """
    pages = (_A4_PORTRAIT,)
    freeform_annotation: tuple[AnnotationSpec, ...] = ((0, "NOTES", (40, 40, 555, 800)),)

    model_path = tmp_path / "freeform-model.pdf"
    _write_pdf(model_path, pages, freeform_annotation)
    markers, signature = read_markers(model_path)

    assert unrecognized_tags(markers) == ["NOTES"]
    auto_profile = generate_candidates(
        "profile-freeform", "format-freeform-essay", signature, markers
    )
    assert auto_profile.regions == (), "no marker on this format matches a known region kind"

    # Manual fallback: a human draws the regions directly, bypassing detection.
    manual_regions = (
        Region(
            region_id="manual-q1",
            kind=RegionKind.QUESTION,
            page_index=0,
            bbox=NormalizedBBox(0.07, 0.05, 0.93, 0.12),
            label="manual:question",
        ),
        Region(
            region_id="manual-answer",
            kind=RegionKind.ANSWER_AREA,
            page_index=0,
            bbox=NormalizedBBox(0.07, 0.13, 0.93, 0.95),
            label="manual:answer_area",
        ),
    )
    manual_draft = Profile.from_candidates(
        "profile-freeform", "format-freeform-essay", signature, manual_regions
    )
    manual_reviewed = [replace(region, confirmed=True) for region in manual_draft.regions]
    confirmed = manual_draft.confirm(manual_reviewed)

    student_path = tmp_path / "freeform-student.pdf"
    _write_pdf(student_path, pages, freeform_annotation)
    _, student_signature = read_markers(student_path)

    applied = reapply_profile(confirmed, "format-freeform-essay-student", student_signature)
    assert len(applied.regions) == 2


def _shrink(bbox: NormalizedBBox, delta: float) -> tuple[float, float, float, float]:
    return (bbox.x0, bbox.y0, bbox.x1 - delta, bbox.y1)
