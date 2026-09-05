"""`adapters.pdf.profile_candidate_generation` -- the Issue #16 candidate
source that supersedes the PoC's tagged-annotation stand-in
(`adapters.pdf.annotation_markers`).

Real PDF text extraction is exercised separately
(`test_text_layout_extraction.py`); these tests fix
`extract_text_lines` to a deterministic set of lines (avoiding the need to
embed Japanese text into a hand-built PDF, which would require a full CID
font -- out of scope here) and a fake `PdfEngine`, so the question-number /
score-pattern matching and region-building logic can be verified precisely.
"""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

import pytest

from auto_scoring.adapters.pdf import profile_candidate_generation as pcg
from auto_scoring.adapters.pdf.text_layout_extraction import TextLine
from auto_scoring.domain.pdf_geometry import PageGeometry
from auto_scoring.domain.profile import ProfileStatus, RegionKind

_A4 = PageGeometry(crop_width=595.0, crop_height=842.0)


class _FakeEngine:
    """A `PdfEngine` stand-in that knows only page count/geometry -- this
    module never rasterizes or reads encryption/page-count directly, it only
    calls `page_count`/`page_geometry`.
    """

    def __init__(self, page_count: int) -> None:
        self._page_count = page_count

    def page_count(self, source: Path) -> int:
        return self._page_count

    def page_geometry(self, source: Path, page_index: int) -> PageGeometry:
        return _A4

    def is_encrypted(self, source: Path) -> bool:
        raise NotImplementedError

    def render_page_png(self, source: Path, page_index: int, *, scale: float) -> bytes:
        raise NotImplementedError

    def stamp_markers(self, *args: object, **kwargs: object) -> None:
        raise NotImplementedError


def _line(text: str, x0: float, y0: float, x1: float, y1: float) -> TextLine:
    return TextLine(text=text, rect_pt=(x0, y0, x1, y1))


class TestQuestionBlocks:
    def test_groups_body_lines_under_their_heading(self, tmp_path: Path) -> None:
        lines_by_page = {
            0: [
                _line("問1 光合成について説明せよ", 72, 700, 300, 720),
                _line("光合成は葉緑体で行われる", 72, 650, 300, 670),
                _line("問2 呼吸について説明せよ", 72, 600, 300, 620),
                _line("呼吸はミトコンドリアで行われる", 72, 550, 300, 570),
            ]
        }
        with patch.object(
            pcg, "extract_text_lines", lambda source, page_index: lines_by_page.get(page_index, [])
        ):
            blocks = pcg._question_blocks(tmp_path / "dummy.pdf", 1)

        assert [block.number for block in blocks] == ["1", "2"]
        assert blocks[0].heading.text == "問1 光合成について説明せよ"
        assert [line.text for line in blocks[0].body] == ["光合成は葉緑体で行われる"]
        assert [line.text for line in blocks[1].body] == ["呼吸はミトコンドリアで行われる"]

    def test_a_page_with_no_heading_produces_no_block(self, tmp_path: Path) -> None:
        lines_by_page = {0: [_line("ただの説明文", 72, 700, 300, 720)]}
        with patch.object(
            pcg, "extract_text_lines", lambda source, page_index: lines_by_page.get(page_index, [])
        ):
            blocks = pcg._question_blocks(tmp_path / "dummy.pdf", 1)
        assert blocks == []

    def test_a_block_does_not_span_a_page_boundary(self, tmp_path: Path) -> None:
        """A question whose body continues past a page break must not pull
        the next page's lines into the same block -- `_model_answer_regions`
        would union rectangles from two pages (possibly different sizes)
        and normalize them through only the heading's own `PageGeometry`.
        """
        lines_by_page = {
            0: [_line("問1 光合成について説明せよ", 72, 700, 300, 720)],
            1: [_line("光合成は葉緑体で行われる、続き", 72, 700, 300, 720)],
        }
        with patch.object(
            pcg, "extract_text_lines", lambda source, page_index: lines_by_page.get(page_index, [])
        ):
            blocks = pcg._question_blocks(tmp_path / "dummy.pdf", 2)

        assert [block.number for block in blocks] == ["1"]
        assert blocks[0].page_index == 0
        # The continuation line on page 2 belongs to no heading -- it is not
        # silently absorbed into page 1's block.
        assert blocks[0].body == []

    def test_heading_at_the_last_line_of_the_last_page_is_still_captured(
        self, tmp_path: Path
    ) -> None:
        # Regression: a heading with no trailing body line (nothing follows
        # it before the loop ends) must still be flushed as its own block.
        lines_by_page = {0: [_line("問9 最後の設問", 72, 700, 300, 720)]}
        with patch.object(
            pcg, "extract_text_lines", lambda source, page_index: lines_by_page.get(page_index, [])
        ):
            blocks = pcg._question_blocks(tmp_path / "dummy.pdf", 1)
        assert [block.number for block in blocks] == ["9"]
        assert blocks[0].body == []


class TestModelAnswerRegions:
    def test_question_with_body_produces_three_regions(self) -> None:
        block = pcg._QuestionBlock(
            number="1",
            page_index=0,
            heading=_line("問1 光合成について説明せよ", 72, 700, 300, 720),
            body=[_line("光合成は葉緑体で行われる", 72, 650, 300, 670)],
        )
        regions = pcg._model_answer_regions([block], [_A4])

        kinds = {region.kind for region in regions}
        assert kinds == {RegionKind.QUESTION, RegionKind.ANSWER_AREA, RegionKind.MODEL_ANSWER}
        for region in regions:
            assert region.label == "1"
            assert region.page_index == 0
            assert not region.confirmed
        question_region = next(r for r in regions if r.kind is RegionKind.QUESTION)
        assert question_region.text == "問1 光合成について説明せよ"
        model_answer_region = next(r for r in regions if r.kind is RegionKind.MODEL_ANSWER)
        assert model_answer_region.text == "光合成は葉緑体で行われる"

    def test_question_with_no_body_produces_only_the_question_region(self) -> None:
        block = pcg._QuestionBlock(
            number="1",
            page_index=0,
            heading=_line("問1 見出しのみ", 72, 700, 300, 720),
            body=[],
        )
        regions = pcg._model_answer_regions([block], [_A4])
        assert [region.kind for region in regions] == [RegionKind.QUESTION]


class TestManualDerivedRegions:
    def test_extracts_rubric_text_and_parsed_score(self) -> None:
        model_block = pcg._QuestionBlock(
            number="1",
            page_index=0,
            heading=_line("問1 光合成について説明せよ", 72, 700, 300, 720),
            body=[_line("光合成は葉緑体で行われる", 72, 650, 300, 670)],
        )
        manual_block = pcg._QuestionBlock(
            number="1",
            page_index=0,
            heading=_line("問1 採点基準", 72, 700, 300, 720),
            body=[
                _line("葉緑体という語を含む", 72, 650, 300, 670),
                _line("5点満点", 72, 600, 300, 620),
            ],
        )
        regions = pcg._manual_derived_regions([model_block], [_A4], [manual_block])

        rubric = next(r for r in regions if r.kind is RegionKind.RUBRIC)
        score = next(r for r in regions if r.kind is RegionKind.SCORE)
        assert rubric.text == "葉緑体という語を含む\n5点満点"
        assert score.text == "5"
        assert rubric.label == "1"
        assert score.label == "1"
        # Anchored to the model-answer question's page, not the manual's own.
        assert rubric.page_index == model_block.page_index
        assert score.page_index == model_block.page_index

    @pytest.mark.parametrize("score_text", ["-5点", "5.5点"])
    def test_a_negative_or_decimal_score_mention_produces_no_score_region(
        self, score_text: str
    ) -> None:
        """A bare `\\d+` would pull "5" out of "-5点"/"5.5点" as if it were
        the real score -- a candidate that looks like a plausible, valid
        value but is actually silently wrong. No SCORE region at all (for a
        human to fill in via `PUT /profile`) is safer than one carrying that
        wrong number (Issue #16 review round 6).
        """
        model_block = pcg._QuestionBlock(
            number="1", page_index=0, heading=_line("問1", 72, 700, 300, 720), body=[]
        )
        manual_block = pcg._QuestionBlock(
            number="1",
            page_index=0,
            heading=_line("問1 採点基準", 72, 700, 300, 720),
            body=[_line(score_text, 72, 650, 300, 670)],
        )
        regions = pcg._manual_derived_regions([model_block], [_A4], [manual_block])
        assert [region.kind for region in regions] == [RegionKind.RUBRIC]

    def test_manual_block_with_no_matching_model_question_is_skipped(self) -> None:
        model_block = pcg._QuestionBlock(
            number="1", page_index=0, heading=_line("問1", 72, 700, 300, 720), body=[]
        )
        manual_block = pcg._QuestionBlock(
            number="2",
            page_index=0,
            heading=_line("問2 採点基準", 72, 700, 300, 720),
            body=[_line("配点3点", 72, 650, 300, 670)],
        )
        regions = pcg._manual_derived_regions([model_block], [_A4], [manual_block])
        assert regions == []

    def test_manual_block_with_no_score_mention_produces_only_rubric(self) -> None:
        model_block = pcg._QuestionBlock(
            number="1", page_index=0, heading=_line("問1", 72, 700, 300, 720), body=[]
        )
        manual_block = pcg._QuestionBlock(
            number="1",
            page_index=0,
            heading=_line("問1 採点基準", 72, 700, 300, 720),
            body=[_line("キーワードを含むこと", 72, 650, 300, 670)],
        )
        regions = pcg._manual_derived_regions([model_block], [_A4], [manual_block])
        assert [region.kind for region in regions] == [RegionKind.RUBRIC]


class TestRectToBbox:
    def test_clips_a_rect_extending_beyond_the_page(self) -> None:
        """PDFium can report a text rectangle that extends beyond the
        page's own CropBox (content clipped/hidden by the viewer but still
        present in the extraction) -- `y1=900` here exceeds `_A4`'s own
        842pt crop_height, and `x0=-10` sits left of the page entirely.
        Normalizing that verbatim would land outside 0..1, which
        `NormalizedBBox` rejects (Issue #16 review round 6).
        """
        bbox = pcg._rect_to_bbox((-10, 700, 300, 900), _A4)
        assert 0.0 <= bbox.x0 < bbox.x1 <= 1.0
        assert 0.0 <= bbox.y0 < bbox.y1 <= 1.0

    def test_clips_a_rect_entirely_off_the_page_without_collapsing(self) -> None:
        """Entirely to the right of the page: both corners normalize past
        1.0 and would clip to the exact same value, which `NormalizedBBox`
        would otherwise reject as having no area.
        """
        bbox = pcg._rect_to_bbox((600, 700, 650, 750), _A4)
        assert 0.0 <= bbox.x0 < bbox.x1 <= 1.0
        assert 0.0 <= bbox.y0 < bbox.y1 <= 1.0


class TestPlaceholderBboxBelow:
    def test_places_below_the_heading_when_room_remains(self) -> None:
        heading = pcg._rect_to_bbox((72, 780, 300, 800), _A4)
        placeholder = pcg._placeholder_bbox_below(heading)
        assert placeholder.y0 == pytest.approx(heading.y1)
        assert placeholder.y1 > placeholder.y0

    def test_places_above_the_heading_when_no_room_below(self) -> None:
        # Near the bottom edge (y1 close to 1.0 in normalized/top-left terms
        # means near the *bottom* of the displayed page here since bbox y
        # grows downward from the top -- pick a heading close to y1=1.0).
        heading = pcg._rect_to_bbox((72, 5, 300, 20), _A4)
        placeholder = pcg._placeholder_bbox_below(heading)
        # Whichever side was chosen, the box must stay within 0..1 and have
        # positive height (NormalizedBBox's own constructor already
        # guarantees this -- constructing it without raising is the check).
        assert 0.0 <= placeholder.y0 < placeholder.y1 <= 1.0


class TestGenerateProfileCandidates:
    def test_builds_a_draft_profile_from_both_pdfs(self, tmp_path: Path) -> None:
        model_lines = {
            0: [
                _line("問1 光合成について説明せよ", 72, 700, 300, 720),
                _line("光合成は葉緑体で行われる", 72, 650, 300, 670),
            ]
        }
        manual_lines = {
            0: [
                _line("問1 採点基準", 72, 700, 300, 720),
                _line("葉緑体という語を含む 5点", 72, 650, 300, 670),
            ]
        }

        def fake_extract(source: Path, page_index: int) -> list[TextLine]:
            if source.name == "model-answer.pdf":
                return model_lines.get(page_index, [])
            return manual_lines.get(page_index, [])

        model_path = tmp_path / "model-answer.pdf"
        manual_path = tmp_path / "manual.pdf"
        model_path.write_bytes(b"%PDF-1.4\n%fake\n")
        manual_path.write_bytes(b"%PDF-1.4\n%fake\n")

        with patch.object(pcg, "extract_text_lines", fake_extract):
            profile = pcg.generate_profile_candidates(
                _FakeEngine(page_count=1), "profile-1", "test-1", model_path, manual_path
            )

        assert profile.status is ProfileStatus.DRAFT
        assert profile.format_id == "test-1"
        assert all(not region.confirmed for region in profile.regions)
        kinds = {region.kind for region in profile.regions}
        assert kinds == {
            RegionKind.QUESTION,
            RegionKind.ANSWER_AREA,
            RegionKind.MODEL_ANSWER,
            RegionKind.RUBRIC,
            RegionKind.SCORE,
        }
        score_region = next(r for r in profile.regions if r.kind is RegionKind.SCORE)
        assert score_region.text == "5"
