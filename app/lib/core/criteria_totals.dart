/// 配点の合計と「不明」の件数を、**画面上の編集中の値から**計算する
/// (Issue #103 受入条件 4)。
///
/// サーバも同じ計算を持っており (`domain.criteria_extraction.criteria_totals`)、
/// `CriteriaResponse.totals` として保存済みの値を返してくる。それを画面に
/// そのまま出さないのは、`TestSettingsPage` が設問依存グラフの実行レイヤを
/// 再計算しているのと同じ理由による: 保存前の編集が 1 つでもあれば、サーバの
/// 値は**もう画面に無いリスト**の合計になる。配点は点数なので、画面の一覧と
/// 合計欄が食い違って見えるのは、そのまま誤った確定につながる。
///
/// **不明は 0 ではない。** [CriteriaTotals.knownPoints] は分かっている配点だけ
/// を足し、[CriteriaTotals.unknownCount] が残りを数える。2 つは常に一緒に
/// 表示すること — 不明を含む一覧の横に合計だけを出すと、それが満点だと読める。
library;

import 'package:auto_scoring_app/api/sidecar_api_client.dart';

/// 配点の集計結果。
class CriteriaTotals {
  const CriteriaTotals({
    required this.knownPoints,
    required this.unknownCount,
    required this.declaredTotalPoints,
    required this.declaredDifference,
  });

  /// 配点が入っている設問の合計。
  final int knownPoints;

  /// 配点が不明のままの設問数。
  final int unknownCount;

  /// 採点基準PDFに書かれていた総得点（満点）。無ければ null。
  final int? declaredTotalPoints;

  /// 総得点と合計の差。**不明が 1 件でも残っている間は null** — その差は
  /// 未入力で既に説明がついており、別の問題として見せると探しに行かせて
  /// しまう。
  final int? declaredDifference;

  /// 全設問に配点が入っているか（＝確定できる状態か）。
  bool get isComplete => unknownCount == 0;
}

/// [questions] と [declaredTotalPoints] から集計する。
///
/// `domain.criteria_extraction.criteria_totals` と同じ規則。どちらかを変える
/// なら両方変えること（`backend/tests/test_criteria_extraction.py` と
/// `app/test/criteria_totals_test.dart` が同じ例で固定している）。
CriteriaTotals criteriaTotals(
  List<CriteriaQuestionModel> questions, {
  int? declaredTotalPoints,
}) {
  var knownPoints = 0;
  var unknownCount = 0;
  for (final question in questions) {
    final points = question.points;
    if (points == null) {
      unknownCount += 1;
    } else {
      knownPoints += points;
    }
  }
  final difference =
      (declaredTotalPoints != null &&
          unknownCount == 0 &&
          declaredTotalPoints != knownPoints)
      ? declaredTotalPoints - knownPoints
      : null;
  return CriteriaTotals(
    knownPoints: knownPoints,
    unknownCount: unknownCount,
    declaredTotalPoints: declaredTotalPoints,
    declaredDifference: difference,
  );
}

/// 確定できない理由。確定できるなら null。
///
/// サーバ側の `ensure_confirmable` と同じ規則を、ボタンを押す前に画面で
/// 示すためのもの。**サーバ側が本体**で、ここはそれを先に見せるだけ
/// （押せてしまっても 422 で止まる）。
String? criteriaBlockingReason(List<CriteriaQuestionModel> questions) {
  if (questions.isEmpty) {
    return '設問が 1 件もありません。抽出をやり直すか、設問を手で追加してください。';
  }
  final unknown = questions.where((q) => q.points == null).length;
  if (unknown > 0) {
    return '配点が不明の設問が $unknown 件あります。すべての配点を入力してください。';
  }
  final nonPositive = questions.where((q) => (q.points ?? 0) <= 0).length;
  if (nonPositive > 0) {
    return '配点が 0 以下の設問が $nonPositive 件あります。1 以上を入力してください。';
  }
  return null;
}

/// 確定済みの依存グラフが、**いまの設問集合**を説明しているか。
///
/// サーバ側 `domain.dependency_graph.can_start_submission_processing` と同じ
/// 規則: 確定済みグラフは不変だが、**テストの設問はそうではない。**
/// 確定後に設問が増減すると、グラフの `question_ids` はもうそのテストを
/// 説明していないのに `status` は `confirmed` のままになる。サーバは
/// その食い違いを「未確定」と同じに扱って `complete-registration` を 409 で
/// 断る。
///
/// **画面が `status` だけを見ると、サーバが断る状態を「残っていることは
/// ありません」と表示してしまう。** 配点を確定すると設問行は作り直されるので、
/// この経路は Issue #103 で新しく踏めるようになった。
///
/// 期待する id は `build_questions_and_rubrics` と同じ合併規則
/// —— 確定済み採点基準の設問番号 ∪ `QUESTION` 領域のラベル —— を
/// `"{testId}:{番号}"` に写したもの。ここが本体ではなく**サーバが本体**で、
/// これは「押す前に気づける」ようにするためのもの。ずれても出るのは警告で、
/// 誤った「全部済み」ではない。
bool dependencyGraphDescribesQuestions({
  required String testId,
  required Iterable<String> graphQuestionIds,
  required Iterable<String> criteriaNumbers,
  required Iterable<String> questionRegionLabels,
}) {
  final expected = <String>{
    for (final number in criteriaNumbers) '$testId:$number',
    for (final label in questionRegionLabels) '$testId:$label',
  };
  final actual = graphQuestionIds.toSet();
  return expected.length == actual.length && expected.containsAll(actual);
}
