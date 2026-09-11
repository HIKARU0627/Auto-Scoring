"""誤答カタログの読み取り（Issue #106）。

**Fixtures are synthetic.** The real 添削資料 hold the tutoring school's
exam prose and the red-pen wording shown to students, and none of it may
appear in a test file (``AGENTS.md`` "Security"). Every grid below is made up;
what is copied from the real material is only its *shape* -- the four column
layouts docs/grading-material-structure.md section 5.1 measured, the header
row that is not row 1, the decorative 「⇒」 column, the 全角/半角 mix.

The property under test throughout: **a file this reader does not understand
must not come back as an empty catalogue.**
"""

from __future__ import annotations

import pytest

from auto_scoring.domain.error_catalog import (
    CatalogEntry,
    CatalogState,
    CatalogUnreadableReason,
    ErrorCatalogDraft,
    ErrorCatalogUnreadable,
    build_error_catalog,
    catalog_state,
    merge_import,
)

# The four measured layouts, as headers only (section 5.1). Values below them
# are invented.
_LAYOUT_A = [
    "回数",
    "問題番号",
    "場所",
    "生徒の誤り方・現状",
    "⇒",
    "伝えるべきこと",
    "採点基準",
    "赤入れ案",
    "重要度（◎、〇、△）",
    "頻度（◎、〇、△）",
]
_LAYOUT_B = [
    "回数",
    "問題番号",
    "生徒の誤り方・現状",
    "伝えるべきこと（添削者が共有しておくべきこと）",
    "減点の有無・幅",
    "赤入れ案",
    "重要度",
    "頻度",
    "備考",
    "",
]
_LAYOUT_C = [
    "回数",
    "問題番号",
    "生徒の誤り方・現状",
    "⇒",
    "採点基準",
    "赤入れ案",
    "重要度（◎、〇、△）",
    "頻度（◎、〇、△）",
    "◎",
    "○",
    "△",
]
_LAYOUT_D = ["回数", "問題番号", "場所", "生徒の誤りの例", "⇒", "赤入れ例"]

_TITLE_ROW = ["架空の講座名", "", "", "", "", "", "", "", "", "", ""]


def test_reads_every_measured_column_layout() -> None:
    """One catalogue out of each of the 4 layouts, with the fields each one
    actually carries -- 減点 present in A/B/C, absent in D."""
    grids = {
        "A": (
            [
                _TITLE_ROW,
                _LAYOUT_A,
                ["第1回", "問1", "", "誤答A", "", "伝達A", "3点減", "赤入れA", "◎", "○"],
            ],
            "3点減",
        ),
        "B": (
            [
                _TITLE_ROW,
                _LAYOUT_B,
                ["第1回", "問1", "誤答A", "伝達A", "適宜減点", "赤入れA", "◎", "○", "", ""],
            ],
            "適宜減点",
        ),
        "C": (
            [
                _TITLE_ROW,
                _LAYOUT_C,
                ["第1回", "問1", "誤答A", "", "部分点なし", "赤入れA", "◎", "○", "", "", ""],
            ],
            "部分点なし",
        ),
        "D": ([_TITLE_ROW, _LAYOUT_D, ["第1回", "問1", "箇所", "誤答A", "", "赤入れA"]], None),
    }
    for layout, (rows, expected_deduction) in grids.items():
        catalog = build_error_catalog([rows])
        assert catalog.entries == (
            CatalogEntry(
                mistake="誤答A",
                red_ink="赤入れA",
                deduction=expected_deduction,
                question_label="問1",
                round_label="第1回",
            ),
        ), layout
        assert catalog.unreadable_sheets == (), layout


def test_header_is_found_below_a_title_block() -> None:
    """The header is not row 1 in any measured file, and the title row above
    it carries a 重要度/頻度 legend with embedded newlines -- which must not
    be mistaken for the header, because it names neither required role."""
    legend = ["架空の講座名", "", "", "", "", "", "", "", "■重要度■\n絶対…", "■頻度■\nよく…"]
    rows = [legend, ["", "", "", "", "", "", "", "", "", ""], _LAYOUT_A]
    rows.append(["第2回", "問3", "", "誤答A", "", "伝達A", "", "赤入れA", "◎", "◎"])
    catalog = build_error_catalog([rows])
    assert [entry.question_label for entry in catalog.entries] == ["問3"]


def test_unknown_columns_are_ignored_and_missing_ones_are_absent() -> None:
    """An extra column costs nothing; a column the layout does not have comes
    back as ``None``, never as an empty string that reads like a value."""
    rows = [
        ["生徒の誤りの例", "赤入れ例", "担当者", "更新日"],
        ["誤答A", "赤入れA", "架空の氏名", "2026-09-10"],
    ]
    (entry,) = build_error_catalog([rows]).entries
    assert entry.deduction is None
    assert entry.question_label is None
    assert entry.round_label is None


def test_full_width_digits_and_trailing_ideographic_space_do_not_split_a_column() -> None:
    """Section 5.1: 全角/半角 mixing and trailing U+3000 inside one file. The
    header match normalizes; the value keeps its own characters but loses the
    padding."""
    rows = [
        ["回数", "問題番号", "生徒の誤り方・現状　", "赤入れ案"],
        ["第１回", "問２", "　誤答A　", "赤入れA"],
    ]
    (entry,) = build_error_catalog([rows]).entries
    assert entry.mistake == "誤答A"
    assert entry.question_label == "問２"


def test_blank_and_short_rows_are_skipped_not_emitted_blank() -> None:
    rows = [
        _LAYOUT_D,
        ["", "", "", "", "", ""],
        ["第1回", "問1", "", "誤答A", "", "赤入れA"],
        ["第1回"],  # a trailing row inside the sheet's used range
    ]
    catalog = build_error_catalog([rows])
    assert len(catalog.entries) == 1


def test_a_row_with_only_one_of_the_two_required_cells_is_still_kept() -> None:
    """Real sheets fill only 赤入れ案 on some rows. Dropping those would be
    exactly the silent loss this reader exists to prevent."""
    rows = [_LAYOUT_D, ["第1回", "問1", "", "", "", "赤入れのみ"]]
    (entry,) = build_error_catalog([rows]).entries
    assert entry.mistake == ""
    assert entry.red_ink == "赤入れのみ"


def test_an_entry_cannot_be_blank_in_both_required_fields() -> None:
    with pytest.raises(ValueError):
        CatalogEntry(mistake="", red_ink="")


class TestUnreadable:
    """The acceptance criterion: 「列構成が想定と違うファイルで、黙って空の
    結果を返さないこと」. Each case raises, and the reason says which shape
    it was -- never an empty success."""

    def test_columns_do_not_match_the_expected_roles(self) -> None:
        rows = [["日付", "担当", "メモ"], ["2026-09-10", "架空の氏名", "自由記述"]]
        with pytest.raises(ErrorCatalogUnreadable) as exc:
            build_error_catalog([rows])
        assert [p.reason for p in exc.value.problems] == [CatalogUnreadableReason.NO_HEADER_ROW]

    def test_only_one_of_the_two_required_columns_is_present(self) -> None:
        """Half a layout is not a layout: a sheet naming 赤入れ案 but no 誤答
        column would otherwise map some other column as the mistake."""
        rows = [["回数", "問題番号", "赤入れ案"], ["第1回", "問1", "赤入れA"]]
        with pytest.raises(ErrorCatalogUnreadable) as exc:
            build_error_catalog([rows])
        assert [p.reason for p in exc.value.problems] == [CatalogUnreadableReason.NO_HEADER_ROW]

    def test_both_roles_named_by_one_single_column(self) -> None:
        """Recognizing the header and mapping its columns is one decision. A
        label naming both roles at once leaves no column for the second, and
        that must come back as an unreadable layout -- not as a crash, and not
        as the two roles pointing at the same cell."""
        rows = [["回数", "誤答と赤入れの記録"], ["第1回", "架空の記述"]]
        with pytest.raises(ErrorCatalogUnreadable) as exc:
            build_error_catalog([rows])
        assert [p.reason for p in exc.value.problems] == [CatalogUnreadableReason.NO_HEADER_ROW]

    def test_header_sits_below_the_search_window(self) -> None:
        rows = [["", ""]] * 10 + [_LAYOUT_D, ["第1回", "問1", "", "誤答A", "", "赤入れA"]]
        with pytest.raises(ErrorCatalogUnreadable):
            build_error_catalog([rows])

    def test_header_with_no_data_under_it(self) -> None:
        with pytest.raises(ErrorCatalogUnreadable) as exc:
            build_error_catalog([[_TITLE_ROW, _LAYOUT_A]])
        assert [p.reason for p in exc.value.problems] == [CatalogUnreadableReason.NO_DATA_ROWS]

    def test_workbook_with_no_sheets(self) -> None:
        with pytest.raises(ErrorCatalogUnreadable) as exc:
            build_error_catalog([])
        assert exc.value.problems == ()

    def test_the_failure_message_names_the_sheet_by_number_not_by_name(self) -> None:
        """Sheet names are content out of the source file and this message
        reaches logs. The number locates the sheet without quoting it."""
        with pytest.raises(ErrorCatalogUnreadable) as exc:
            build_error_catalog([[["日付"]], [["メモ"]]])
        assert [p.sheet_number for p in exc.value.problems] == [1, 2]
        assert "sheet 1" in str(exc.value) and "sheet 2" in str(exc.value)


def test_a_sheet_that_fails_inside_a_readable_workbook_is_reported_not_dropped() -> None:
    """The partial-read case. A legend sheet next to a table sheet still
    produces a catalogue, and the sheet that gave nothing is visible on the
    result -- so a caller can never read "1 sheet read" as "the whole
    workbook read"."""
    legend = [["記号", "意味"], ["◎", "架空の説明"]]
    table = [_LAYOUT_D, ["第1回", "問1", "", "誤答A", "", "赤入れA"]]
    catalog = build_error_catalog([legend, table])
    assert len(catalog.entries) == 1
    assert [(p.sheet_number, p.reason) for p in catalog.unreadable_sheets] == [
        (1, CatalogUnreadableReason.NO_HEADER_ROW)
    ]


def test_merge_import_keeps_an_edited_row_and_takes_the_fresh_otherwise() -> None:
    """Issue #209 judgment 2: a re-import must not discard a human correction,
    and must not keep an untouched row in place of the file's newer one."""
    existing = [
        CatalogEntry(mistake="人の訂正", red_ink="人の赤入れ", edited=True),
        CatalogEntry(mistake="機械の古い行", red_ink="機械の赤入れ", edited=False),
    ]
    imported = [
        CatalogEntry(mistake="ファイルA", red_ink="赤入れA"),
        CatalogEntry(mistake="ファイルB", red_ink="赤入れB"),
    ]
    merged = merge_import(existing, imported, overwrite_edited=False)
    assert [entry.mistake for entry in merged] == ["人の訂正", "ファイルB"]


def test_merge_import_overwrite_takes_the_file_wholesale() -> None:
    existing = [CatalogEntry(mistake="人の訂正", red_ink="人の赤入れ", edited=True)]
    imported = [CatalogEntry(mistake="ファイルA", red_ink="赤入れA")]
    merged = merge_import(existing, imported, overwrite_edited=True)
    assert [(entry.mistake, entry.edited) for entry in merged] == [("ファイルA", False)]


def test_catalog_state_separates_the_three_no_catalogue_situations() -> None:
    """(c) を (a) と同じ値にしない -- the point Issue #106 was written for."""
    not_registered = catalog_state(has_annotation_resource=False, has_excel=False, imported=False)
    word_only = catalog_state(has_annotation_resource=True, has_excel=False, imported=False)
    unreadable = catalog_state(has_annotation_resource=True, has_excel=True, imported=False)
    available = catalog_state(has_annotation_resource=True, has_excel=True, imported=True)
    assert len({not_registered, word_only, unreadable, available}) == 4
    assert (not_registered, word_only, unreadable, available) == (
        CatalogState.NOT_REGISTERED,
        CatalogState.WORD_ONLY,
        CatalogState.UNREADABLE,
        CatalogState.AVAILABLE,
    )


def test_a_draft_round_trips_through_its_json_shape() -> None:
    draft = ErrorCatalogDraft(
        test_id="t",
        entries=(CatalogEntry(mistake="m", red_ink="r", edited=True),),
        revision=3,
        imported=True,
    )
    assert ErrorCatalogDraft.from_dict(draft.to_dict()) == draft
