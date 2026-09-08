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
