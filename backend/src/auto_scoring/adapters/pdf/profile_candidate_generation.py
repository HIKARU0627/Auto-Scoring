"""Generate DRAFT profile candidates from a test's two registration PDFs
(Issue #16).

Supersedes `adapters.pdf.annotation_markers` (Issue #15/PoC 4's tagged-square
stand-in) as the actual candidate source for test registration --
`annotation_markers` stays in place only for its own PoC regression tests
(see docs/poc-4-multi-layout-profiles.md "PoC限定・要再確認"). Like the
heuristic dependency analyzer (Issue #26), a real AI/OCR-backed extraction
remains PoC-pending (docs/technology-stack.md §3.5); this is a
deterministic, offline stand-in that looks for a question-number pattern
("問1", "大問2", ...) in each page's text lines and buckets the text
following it into that question's answer/rubric/model-answer candidates.

Every region this produces is unconfirmed -- `Profile.from_candidates`
enforces that -- and a human must review, correct and confirm it before
`domain.test_registration.build_questions_and_rubrics` can turn it into real
`Question`/`Rubric` rows.

Design decision (recorded in docs/test-registration.md): the marking-manual
PDF is a *separate* document from the model-answer PDF, with its own page
layout the profile's `FormatSignature` does not describe (the signature
describes the model-answer/submission format, since that is what
`profile_apply.reapply_profile` matches submissions against). A manual-
derived `RUBRIC`/`SCORE` region therefore cannot carry the manual PDF's own
coordinates -- they would reference a page/position that has nothing to do
with the model-answer format the profile is bound to. Instead, such regions
are anchored to the *model-answer* page and placed directly below the
matching question's heading, as an explicit placeholder position for a human
to move; only their extracted text (the rubric wording, the parsed score) is
trusted from the manual PDF itself.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from auto_scoring.adapters.pdf.text_layout_extraction import RectPt, TextLine, extract_text_lines
from auto_scoring.domain.pdf_engine import PdfEngine
from auto_scoring.domain.pdf_geometry import PageGeometry, UserSpacePoint, user_space_to_normalized
from auto_scoring.domain.profile import (
    FormatSignature,
    NormalizedBBox,
    PageFormat,
    Profile,
    Region,
    RegionKind,
)

#: Matches a question-number heading like "問1", "問 12", "大問3". The
#: captured group is used as `Region.label` -- the same key
#: `domain.test_registration.build_questions_and_rubrics` groups regions by.
_QUESTION_NUMBER_PATTERN = re.compile(r"(?:問|大問)\s*(\d+)")

#: Matches a marking-manual score mention like "5点" or "10 点満点". The
#: captured group becomes the `SCORE` region's text (parsed as an int by
#: `domain.test_registration._extract_points`). Excludes a digit run
#: immediately preceded by `-`/`.`/another digit -- a bare `\d+` would pull
#: "5" out of "-5点" or "5.5点" as if it were the real score, silently
#: offering a plausible-looking but wrong candidate value instead of no
#: match at all (the same boundary `domain.test_registration
#: ._SCORE_NUMBER_PATTERN` applies at confirm time -- this just applies it
#: earlier, before an unreviewed value even becomes a candidate, so a
#: reviewer who accepts candidates without editing every field can't ship a
#: silently-wrong score, Issue #16 review round 6).
_SCORE_PATTERN = re.compile(r"(?<![-.\d])(\d+)\s*点")

#: Placeholder height (normalized) for a manual-derived region anchored under
#: a question heading -- purely a starting position for human review to move.
_PLACEHOLDER_HEIGHT = 0.03


@dataclass(frozen=True)
class _QuestionBlock:
    """One detected question heading and the text lines that follow it, up
    to (but excluding) the next detected heading or the end of the page.
    """

    number: str
    page_index: int
    heading: TextLine
    body: list[TextLine]


#: Minimum width/height `_rect_to_bbox` nudges a clipped-to-nothing bbox
#: apart to -- small enough to be visually negligible once a human is
#: reviewing/moving it, large enough that `NormalizedBBox`'s own
#: positive-area check never rejects it.
_MIN_CLIPPED_BBOX_SIZE = 1e-6


def _clip_unit(value: float) -> float:
    return max(0.0, min(1.0, value))


def _rect_to_bbox(rect_pt: RectPt, geometry: PageGeometry) -> NormalizedBBox:
    """PDF user-space rectangle -> normalized bbox (see `profile_detection.rect_to_bbox`,
    duplicated here to avoid a cross-import between the two candidate-generation modules).

    Clipped to the displayed page (`0..1`): a valid PDF can contain text
    that PDFium's own text-rect extraction reports slightly outside the
    page's `CropBox` (e.g. clipped or hidden content still present in the
    extraction) -- normalizing that verbatim can land outside `0..1`, which
    `NormalizedBBox` rejects with a `ValueError` `analyze_profile` doesn't
    translate, turning one such line into an unhandled 500 for the whole
    analysis (Issue #16 review round 6). A region a human can still
    review/move is safer than aborting the whole run over one line. If
    clipping collapses a side to zero width/height (the rect was entirely
    off-page on that axis), nudge it apart by `_MIN_CLIPPED_BBOX_SIZE`
    rather than let `NormalizedBBox` reject the degenerate box outright.
    """
    x0, y0, x1, y1 = rect_pt
    corners = (
        user_space_to_normalized(UserSpacePoint(x, y), geometry)
        for x, y in ((x0, y0), (x0, y1), (x1, y0), (x1, y1))
    )
    xs: list[float] = []
    ys: list[float] = []
    for point in corners:
        xs.append(point.x)
        ys.append(point.y)
    x0_n, x1_n = _clip_unit(min(xs)), _clip_unit(max(xs))
    y0_n, y1_n = _clip_unit(min(ys)), _clip_unit(max(ys))
    if x1_n <= x0_n:
        x0_n = max(0.0, x0_n - _MIN_CLIPPED_BBOX_SIZE)
        x1_n = min(1.0, x0_n + 2 * _MIN_CLIPPED_BBOX_SIZE)
    if y1_n <= y0_n:
        y0_n = max(0.0, y0_n - _MIN_CLIPPED_BBOX_SIZE)
        y1_n = min(1.0, y0_n + 2 * _MIN_CLIPPED_BBOX_SIZE)
    return NormalizedBBox(x0=x0_n, y0=y0_n, x1=x1_n, y1=y1_n)


def _page_geometries(engine: PdfEngine, source: Path, page_count: int) -> list[PageGeometry]:
    return [engine.page_geometry(source, index) for index in range(page_count)]


def _format_signature(geometries: list[PageGeometry]) -> FormatSignature:
    return FormatSignature(
        pages=tuple(
            PageFormat(width_pt=g.displayed_width, height_pt=g.displayed_height) for g in geometries
        )
    )


def _question_blocks(source: Path, page_count: int) -> list[_QuestionBlock]:
    """One block per detected heading, never spanning a page boundary.

    A question's body that continues past a page break (no new heading
    appears before the next page starts) is cut off at the end of the
    heading's own page, rather than folding the next page's lines into the
    same block. `_model_answer_regions`/`_manual_derived_regions` union a
    block's body rectangles and normalize them through a single page's
    `PageGeometry`; letting a block span two pages of potentially different
    size would union rectangles from two different coordinate spaces and
    silently produce a wrong (or out-of-range) region (Issue #16 review).
    """
    blocks: list[_QuestionBlock] = []
    current: _QuestionBlock | None = None
    for page_index in range(page_count):
        for line in extract_text_lines(source, page_index):
            match = _QUESTION_NUMBER_PATTERN.search(line.text)
            if match is not None:
                if current is not None:
                    blocks.append(current)
                current = _QuestionBlock(
                    number=match.group(1), page_index=page_index, heading=line, body=[]
                )
            elif current is not None:
                current.body.append(line)
        # Flush at the page boundary, before moving to the next page's
        # lines: a block's body never crosses into a different page.
        if current is not None:
            blocks.append(current)
            current = None
    return blocks


def _union_rect(lines: list[TextLine]) -> RectPt:
    lefts = [line.rect_pt[0] for line in lines]
    bottoms = [line.rect_pt[1] for line in lines]
    rights = [line.rect_pt[2] for line in lines]
    tops = [line.rect_pt[3] for line in lines]
    return (min(lefts), min(bottoms), max(rights), max(tops))


def _placeholder_bbox_below(heading_bbox: NormalizedBBox) -> NormalizedBBox:
    """A small normalized box directly under `heading_bbox`, clamped to the page.

    Used for manual-derived regions that have no coordinates of their own on
    the model-answer page (see the module docstring) -- purely a starting
    position a human moves during review.
    """
    if heading_bbox.y1 + _PLACEHOLDER_HEIGHT <= 1.0:
        y0, y1 = heading_bbox.y1, heading_bbox.y1 + _PLACEHOLDER_HEIGHT
    else:
        y0, y1 = max(0.0, heading_bbox.y0 - _PLACEHOLDER_HEIGHT), heading_bbox.y0
    return NormalizedBBox(x0=heading_bbox.x0, y0=y0, x1=heading_bbox.x1, y1=y1)


def _model_answer_regions(
    blocks: list[_QuestionBlock], geometries: list[PageGeometry]
) -> list[Region]:
    regions: list[Region] = []
    for index, block in enumerate(blocks):
        geometry = geometries[block.page_index]
        regions.append(
            Region(
                region_id=f"question-{block.number}-{index}",
                kind=RegionKind.QUESTION,
                page_index=block.page_index,
                bbox=_rect_to_bbox(block.heading.rect_pt, geometry),
                label=block.number,
                text=block.heading.text,
            )
        )
        if not block.body:
            continue
        body_bbox = _rect_to_bbox(_union_rect(block.body), geometry)
        body_text = "\n".join(line.text for line in block.body)
        regions.append(
            Region(
                region_id=f"answer-area-{block.number}-{index}",
                kind=RegionKind.ANSWER_AREA,
                page_index=block.page_index,
                bbox=body_bbox,
                label=block.number,
            )
        )
        regions.append(
            Region(
                region_id=f"model-answer-{block.number}-{index}",
                kind=RegionKind.MODEL_ANSWER,
                page_index=block.page_index,
                bbox=body_bbox,
                label=block.number,
                text=body_text,
            )
        )
    return regions


def _manual_derived_regions(
    model_blocks: list[_QuestionBlock],
    model_geometries: list[PageGeometry],
    manual_blocks: list[_QuestionBlock],
) -> list[Region]:
    """`RUBRIC`/`SCORE` regions built from the manual PDF's text, anchored to
    the matching question's position on the *model-answer* page (see the
    module docstring for why the manual PDF's own coordinates cannot be used
    directly).
    """
    manual_by_number = {block.number: block for block in manual_blocks}
    regions: list[Region] = []
    for index, model_block in enumerate(model_blocks):
        manual_block = manual_by_number.get(model_block.number)
        if manual_block is None or not manual_block.body:
            continue
        heading_bbox = _rect_to_bbox(
            model_block.heading.rect_pt, model_geometries[model_block.page_index]
        )
        placeholder = _placeholder_bbox_below(heading_bbox)
        rubric_text = "\n".join(line.text for line in manual_block.body)
        regions.append(
            Region(
                region_id=f"rubric-{model_block.number}-{index}",
                kind=RegionKind.RUBRIC,
                page_index=model_block.page_index,
                bbox=placeholder,
                label=model_block.number,
                text=rubric_text,
            )
        )
        score_line = next(
            (line for line in manual_block.body if _SCORE_PATTERN.search(line.text)), None
        )
        if score_line is None:
            continue
        score_match = _SCORE_PATTERN.search(score_line.text)
        assert score_match is not None  # guaranteed by the `next(...)` filter above
        regions.append(
            Region(
                region_id=f"score-{model_block.number}-{index}",
                kind=RegionKind.SCORE,
                page_index=model_block.page_index,
                bbox=placeholder,
                label=model_block.number,
                text=score_match.group(1),
            )
        )
    return regions


def generate_profile_candidates(
    engine: PdfEngine,
    profile_id: str,
    test_id: str,
    model_answer_path: Path,
    manual_path: Path,
) -> Profile:
    """Build a DRAFT profile from the model-answer and marking-manual PDFs.

    The profile's `FormatSignature` describes the model-answer PDF's page
    layout -- the shape `profile_apply.reapply_profile` later matches student
    submissions against. The manual PDF only contributes text (rubric
    wording, parsed scores); see the module docstring for why its own
    regions are anchored to the model-answer page instead of their own.
    """
    model_page_count = engine.page_count(model_answer_path)
    model_geometries = _page_geometries(engine, model_answer_path, model_page_count)
    signature = _format_signature(model_geometries)

    manual_page_count = engine.page_count(manual_path)

    model_blocks = _question_blocks(model_answer_path, model_page_count)
    manual_blocks = _question_blocks(manual_path, manual_page_count)

    regions = _model_answer_regions(model_blocks, model_geometries)
    regions += _manual_derived_regions(model_blocks, model_geometries, manual_blocks)

    return Profile.from_candidates(profile_id, test_id, signature, regions)
