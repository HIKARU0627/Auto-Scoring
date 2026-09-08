"""Rule-based role proposals for a scanned batch (Issue #101).

The core of this file is `test_every_observed_naming_hazard_still_matches`:
seven distinct ways the real material's file names break a naive matcher were
recorded in Issue #101, and each one is exercised here **with a synthetic
name**. No name, course title or subject word from the real material appears
in this repository (`AGENTS.md` "Security", the batch's own handling rules).
"""

from __future__ import annotations

import pytest

from auto_scoring.domain.intake_template import (
    DEFAULT_TEMPLATE,
    IntakeRule,
    IntakeTemplate,
    IntakeTemplateError,
    MaterialRole,
    Requirement,
    RuleScope,
    ScannedFile,
    classify_by_rules,
    matches_pattern,
    normalize_for_matching,
)

_DIGEST = "0" * 64


def _scanned(relative_path: str) -> ScannedFile:
    return ScannedFile(relative_path=relative_path, size_bytes=1, sha256=_DIGEST)


def _roles(paths: list[str], template: IntakeTemplate = DEFAULT_TEMPLATE) -> list[object]:
    return [a.role for a in classify_by_rules([_scanned(p) for p in paths], template)]


# --------------------------------------------------------------------------- #
# The seven observed hazards
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    ("hazard", "relative_path", "expected"),
    [
        (
            "whitespace immediately before the extension",
            "subject-a/01_answers .pdf",
            MaterialRole.STUDENT_ANSWER,
        ),
        (
            "doubled extension",
            "subject-a/02_criteria.pdf.pdf",
            MaterialRole.GRADING_CRITERIA,
        ),
        (
            "suffix after the role word",
            "subject-a/02_criteria(A3-B1).pdf",
            MaterialRole.GRADING_CRITERIA,
        ),
        (
            "hyphen separator instead of underscore",
            "subject-a/04-1_sample.pdf",
            MaterialRole.ANNOTATION_SAMPLE,
        ),
        (
            "underscore separator instead of hyphen",
            "subject-a/04_1_sample.pdf",
            MaterialRole.ANNOTATION_SAMPLE,
        ),
        (
            "circled sample number",
            "subject-a/04_①.pdf",
            MaterialRole.ANNOTATION_SAMPLE,
        ),
        (
            "companion notes file",
            "subject-a/how-to-use.txt",
            MaterialRole.IGNORE,
        ),
    ],
)
def test_every_observed_naming_hazard_still_matches(
    hazard: str, relative_path: str, expected: MaterialRole
) -> None:
    assert _roles([relative_path]) == [expected], hazard


def test_a_subject_word_in_the_name_never_decides_the_role() -> None:
    """One subject's sample file is named after a *different* subject's course
    in the real material, because the two share a task.

    So two files whose only difference is the subject word must get the same
    proposal: the serial prefix decides, the subject word is not evidence.
    """
    assert _roles(["subject-a/04_1_alpha-course.pdf", "subject-b/04_1_beta-course.pdf"]) == [
        MaterialRole.ANNOTATION_SAMPLE,
        MaterialRole.ANNOTATION_SAMPLE,
    ]


def test_whitespace_and_doubled_extension_together_collapse() -> None:
    assert normalize_for_matching("01_answers.pdf .pdf") == "01_answers.pdf"


def test_a_genuine_multi_part_extension_is_not_collapsed() -> None:
    """Only an extension repeated verbatim is a doubling; ``.tar.gz`` is a real
    two-part name and must survive.
    """
    assert normalize_for_matching("archive.tar.gz") == "archive.tar.gz"


# --------------------------------------------------------------------------- #
# Matching semantics
# --------------------------------------------------------------------------- #
def test_a_file_no_rule_matches_gets_no_role_rather_than_a_default() -> None:
    """``None`` means "no rule matched", which is what routes the file to LLM
    classification and then to a human. A default role here would silently
    import a file as something nobody chose.
    """
    assert _roles(["subject-a/notes.pdf"]) == [None]


def test_first_matching_rule_wins_so_rule_order_is_meaning() -> None:
    template = IntakeTemplate(
        id="t",
        name="ordered",
        rules=(
            IntakeRule(scope=RuleScope.FILE, pattern="01_*", role=MaterialRole.STUDENT_ANSWER),
            IntakeRule(scope=RuleScope.FILE, pattern="*", role=MaterialRole.REFERENCE),
        ),
    )
    assert _roles(["01_x.pdf", "other.pdf"], template) == [
        MaterialRole.STUDENT_ANSWER,
        MaterialRole.REFERENCE,
    ]


def test_a_folder_rule_covers_every_file_inside_it() -> None:
    """This is what keeps forty answers from costing forty clicks: one rule,
    one row on the confirmation screen (Issue #101).
    """
    template = IntakeTemplate(
        id="t",
        name="folder",
        rules=(
            IntakeRule(
                scope=RuleScope.FOLDER,
                pattern="answers",
                role=MaterialRole.STUDENT_ANSWER,
                requirement=Requirement.REQUIRED,
            ),
        ),
    )
    paths = [f"answers/scan-{index}.pdf" for index in range(40)]
    assert _roles(paths, template) == [MaterialRole.STUDENT_ANSWER] * 40


def test_a_folder_rule_does_not_claim_files_at_the_top_level() -> None:
    """A file directly under the chosen folder has no containing folder name;
    treating that as the empty string would let ``*`` claim it.
    """
    template = IntakeTemplate(
        id="t",
        name="folder",
        rules=(IntakeRule(scope=RuleScope.FOLDER, pattern="*", role=MaterialRole.REFERENCE),),
    )
    assert _roles(["loose.pdf", "inside/loose.pdf"], template) == [
        None,
        MaterialRole.REFERENCE,
    ]


def test_bracket_characters_in_a_pattern_match_themselves() -> None:
    """Normalization folds ``-`` onto ``_``, which would corrupt a regex/glob
    character range. Only ``*`` and ``?`` are wildcards, so a bracket is a
    literal and cannot be broken by that folding.
    """
    assert matches_pattern("02_criteria[A-B].pdf", "02_criteria[A_B].pdf")
    assert not matches_pattern("02_criteria[A-B].pdf", "02_criteriaA.pdf")


def test_matching_is_case_insensitive_on_the_extension() -> None:
    assert _roles(["subject-a/01_answers.PDF"]) == [MaterialRole.STUDENT_ANSWER]


# --------------------------------------------------------------------------- #
# Template validation
# --------------------------------------------------------------------------- #
def test_default_template_requires_answers_and_criteria() -> None:
    assert DEFAULT_TEMPLATE.required_roles() == (
        MaterialRole.STUDENT_ANSWER,
        MaterialRole.GRADING_CRITERIA,
    )


def test_an_ignore_rule_cannot_be_required() -> None:
    """Otherwise the screen would report a group as incomplete for a role that
    is, by definition, never imported.
    """
    with pytest.raises(IntakeTemplateError):
        IntakeRule(
            scope=RuleScope.FILE,
            pattern="*.txt",
            role=MaterialRole.IGNORE,
            requirement=Requirement.REQUIRED,
        )


def test_blank_pattern_is_rejected() -> None:
    with pytest.raises(IntakeTemplateError):
        IntakeRule(scope=RuleScope.FILE, pattern="   ", role=MaterialRole.REFERENCE)


@pytest.mark.parametrize("relative_path", ["/absolute.pdf", "../escape.pdf", "a/../../escape.pdf"])
def test_a_path_outside_the_chosen_folder_is_rejected(relative_path: str) -> None:
    with pytest.raises(IntakeTemplateError):
        _scanned(relative_path)


def test_sha256_must_be_a_lowercase_hex_digest() -> None:
    with pytest.raises(IntakeTemplateError):
        ScannedFile(relative_path="a.pdf", size_bytes=1, sha256="not-a-digest")
