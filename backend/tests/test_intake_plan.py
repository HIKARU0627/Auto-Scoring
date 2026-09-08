"""Grouping, cost estimation and requirement checks for a scanned batch
(Issue #101).

Two acceptance criteria are pinned here directly:

* #8 -- a file a rule matched must not be counted as needing an LLM call
  (`test_a_rule_matched_file_is_never_counted_as_needing_an_llm_call`; the
  matching "the classifier is never *called*" assertion lives in
  `test_intake_api.py`, which owns the call path).
* follow-up A -- a folder holding only answers must be importable into a test
  that already exists, without a grading-criteria file
  (`test_a_group_bound_to_an_existing_test_needs_no_grading_criteria`).

All file names are synthetic.
"""

from __future__ import annotations

from dataclasses import replace

import pytest

from auto_scoring.domain.intake_plan import (
    ClassificationNeed,
    GroupTarget,
    GroupTargetKind,
    RoleSource,
    build_plan,
    unmet_requirements,
)
from auto_scoring.domain.intake_template import (
    DEFAULT_TEMPLATE,
    MaterialRole,
    ScannedFile,
)

_ELEVEN_SUBJECT_BATCH = [
    path
    for index in range(11)
    for path in (
        f"subject-{index:02d}/01_answers.pdf",
        f"subject-{index:02d}/02_criteria.pdf",
        f"subject-{index:02d}/03_resource.xls",
        f"subject-{index:02d}/04_1_sample.pdf",
        f"subject-{index:02d}/how-to-use.txt",
    )
]


def _scanned(paths: list[str]) -> list[ScannedFile]:
    # A distinct digest per path, so cache assertions can target one file.
    return [
        ScannedFile(
            relative_path=path,
            size_bytes=1024,
            sha256=f"{index:064x}",
        )
        for index, path in enumerate(paths)
    ]


# --------------------------------------------------------------------------- #
# Grouping (acceptance criteria 1 and 2)
# --------------------------------------------------------------------------- #
def test_choosing_the_parent_of_eleven_folders_yields_eleven_groups() -> None:
    plan = build_plan(_scanned(_ELEVEN_SUBJECT_BATCH), DEFAULT_TEMPLATE, root_name="batch")
    assert len(plan.groups) == 11
    assert [group.suggested_name for group in plan.groups] == [
        f"subject-{index:02d}" for index in range(11)
    ]
    assert all(not group.missing_required_roles_if_new for group in plan.groups)


def test_choosing_a_single_folder_yields_one_group() -> None:
    plan = build_plan(
        _scanned(["01_answers.pdf", "02_criteria.pdf"]),
        DEFAULT_TEMPLATE,
        root_name="one-subject",
    )
    assert len(plan.groups) == 1
    assert plan.groups[0].suggested_name == "one-subject"
    assert plan.groups[0].missing_required_roles_if_new == ()


def test_splitting_can_be_turned_off_to_make_one_test_of_everything() -> None:
    template = replace(DEFAULT_TEMPLATE, split_child_directories=False)
    plan = build_plan(_scanned(_ELEVEN_SUBJECT_BATCH), template, root_name="batch")
    assert len(plan.groups) == 1
    assert plan.groups[0].suggested_name == "batch"


def test_nesting_deeper_than_one_level_still_groups_by_the_top_folder() -> None:
    plan = build_plan(
        _scanned(["subject-a/scans/01_answers.pdf", "subject-a/02_criteria.pdf"]),
        DEFAULT_TEMPLATE,
        root_name="batch",
    )
    assert len(plan.groups) == 1
    assert plan.groups[0].key == "subject-a"


# --------------------------------------------------------------------------- #
# Cost estimation (acceptance criteria 7 and 8)
# --------------------------------------------------------------------------- #
def test_a_rule_matched_file_is_never_counted_as_needing_an_llm_call() -> None:
    plan = build_plan(_scanned(_ELEVEN_SUBJECT_BATCH), DEFAULT_TEMPLATE, root_name="batch")
    assert plan.estimate.pending == 0
    assert plan.estimate.not_needed == len(_ELEVEN_SUBJECT_BATCH)
    assert all(
        planned.classification is ClassificationNeed.NOT_NEEDED
        and planned.role_source is RoleSource.RULE
        for group in plan.groups
        for planned in group.files
    )


def test_an_unmatched_pdf_is_pending_and_an_unmatched_spreadsheet_is_unsupported() -> None:
    """Only PDFs can be rendered to a page image, so a stray spreadsheet
    cannot be classified by a model at all. Saying so beats counting it into
    an estimate that would never be spent.
    """
    plan = build_plan(_scanned(["stray.pdf", "stray.xls"]), DEFAULT_TEMPLATE, root_name="batch")
    files = {planned.relative_path: planned for planned in plan.groups[0].files}
    assert files["stray.pdf"].classification is ClassificationNeed.PENDING
    assert files["stray.xls"].classification is ClassificationNeed.UNSUPPORTED
    assert plan.estimate.pending == 1
    assert plan.estimate.unsupported == 1
    assert files["stray.pdf"].role is None
    assert files["stray.pdf"].role_source is RoleSource.UNRESOLVED


def test_a_digest_already_classified_is_not_charged_for_again() -> None:
    """Re-importing the same content must not ask the reviewer, or the
    provider, the same question twice.
    """
    scanned = _scanned(["stray.pdf"])
    plan = build_plan(
        scanned, DEFAULT_TEMPLATE, root_name="batch", cached_digests=[scanned[0].sha256]
    )
    assert plan.groups[0].files[0].classification is ClassificationNeed.CACHED
    assert plan.estimate.pending == 0
    assert plan.estimate.cached == 1


# --------------------------------------------------------------------------- #
# Requirements (follow-up A: the weekly "answers only" folder)
# --------------------------------------------------------------------------- #
def test_a_new_test_reports_missing_grading_criteria() -> None:
    plan = build_plan(_scanned(["01_answers.pdf"]), DEFAULT_TEMPLATE, root_name="week-2")
    group = plan.groups[0]
    assert group.missing_required_roles_if_new == (MaterialRole.GRADING_CRITERIA,)
    assert unmet_requirements(
        group,
        GroupTarget(kind=GroupTargetKind.NEW),
        required_roles=DEFAULT_TEMPLATE.required_roles(),
    ) == (MaterialRole.GRADING_CRITERIA,)


def test_a_group_bound_to_an_existing_test_needs_no_grading_criteria() -> None:
    """The weekly flow: criteria were registered once, answers arrive later.

    Without this, week two is blocked -- the reviewer would be told their
    answers-only folder is incomplete when the criteria already exist on the
    test they are adding to.
    """
    plan = build_plan(_scanned(["01_answers.pdf"]), DEFAULT_TEMPLATE, root_name="week-2")
    assert (
        unmet_requirements(
            plan.groups[0],
            GroupTarget(kind=GroupTargetKind.EXISTING, test_id="test-1"),
            required_roles=DEFAULT_TEMPLATE.required_roles(),
        )
        == ()
    )


def test_an_existing_target_must_name_a_test() -> None:
    with pytest.raises(ValueError):
        GroupTarget(kind=GroupTargetKind.EXISTING)


def test_a_new_target_must_not_name_a_test() -> None:
    with pytest.raises(ValueError):
        GroupTarget(kind=GroupTargetKind.NEW, test_id="test-1")
