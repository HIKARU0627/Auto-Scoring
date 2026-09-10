/// Which 回答欄 (answer areas) a test's profile still needs, derived from the
/// working copy of its regions rather than the last server response.
///
/// Extracted from `features/test_registration/test_settings_page.dart`
/// (Issue #126): `TestSettingsPage` recomputes these on every build so an
/// edit -- assigning a question, drawing a box, deleting one -- is reflected
/// immediately rather than after the next round trip, and that recomputation
/// has no need of a `BuildContext` or a `Widget`. Kept in its own file,
/// separate from `core/criteria_totals.dart` (配点) and
/// `core/dependency_dag.dart` (依存グラフ): #103 and #105 already collided by
/// sharing one page-level file, and 回答欄 is the concern Issue #108 (答案が
/// 2ページにまたがる場合) will extend next.
library;

import 'package:auto_scoring_app/api/sidecar_api_client.dart';

/// The questions with no 回答欄, split by *why* (Issue #164).
///
/// [regions] is the working copy being edited, so membership follows every
/// click without waiting for a save. [reportedAbsent] is the last server
/// response's `ProfileResponse.absentQuestionNumbers` -- what detection said,
/// which does not change as the reviewer edits -- so a question the reviewer
/// draws a box for leaves both lists on the click, without the stored claim
/// having to be rewritten.
({List<String> undetected, List<String> absent}) missingAnswerAreas({
  required List<RegionModel> regions,
  required List<String> questionNumbers,
  required Set<String> reportedAbsent,
}) {
  final covered = {
    for (final region in regions)
      if (region.kind == RegionKind.answerArea) region.label,
  };
  final undetected = <String>[];
  final absent = <String>[];
  for (final number in questionNumbers) {
    if (covered.contains(number)) continue;
    (reportedAbsent.contains(number) ? absent : undetected).add(number);
  }
  return (undetected: undetected, absent: absent);
}

/// Answer areas that name no confirmed question. These block the confirm --
/// `build_questions_and_rubrics` ignores them without a word.
List<RegionModel> unassignedAnswerAreas({
  required List<RegionModel> regions,
  required Set<String> knownQuestionNumbers,
}) => [
  for (final region in regions)
    if (region.kind == RegionKind.answerArea &&
        !knownQuestionNumbers.contains(region.label))
      region,
];

/// Whether the answer sheet the regions are drawn on is actually on screen.
///
/// Confirming answer-area coordinates is attesting to where they sit on a
/// page. Doing that against blank outlines is confirming something nobody
/// looked at, so it is refused while any answer area exists and the sheet is
/// not displayed (review round 1, P1; Issue #85's rule).
bool mustSeeAnswerSheetFirst({
  required bool answerSheetVisible,
  required List<RegionModel> regions,
}) =>
    !answerSheetVisible &&
    regions.any((region) => region.kind == RegionKind.answerArea);
