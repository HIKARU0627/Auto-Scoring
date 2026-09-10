/// 設問をレビューする順番。**この順を決める場所は1つしかない** (Issue #145)。
///
/// 添削レビュー画面 (1設問ずつ) と答案確定画面 (全設問を1画面) は同じ答案の
/// 同じ設問を並べる。**2か所で別々に並べると、確定画面の3枚目とレールの3番目が
/// 別の設問になる。** そうなった瞬間、「問3を見た」という記録がどの設問について
/// のものか分からなくなる -- 見ていないものを確定させないための到達判定
/// (Issue #85) が、順番のずれ1つで嘘になる。`core/review_queue.dart` が答案の
/// 並び順について同じことを言っているのと、まったく同じ理由である。
///
/// ウィジェットを持たないので `question_order_test.dart` から直接読める。
library;

import 'package:auto_scoring_app/api/sidecar_api_client.dart';

/// [value] を ASCII 数字の連なりとそれ以外の連なりに交互に割る。
/// 例: `"1a"` -> `["1", "a"]`、`"問10"` -> `["問", "10"]`。
/// [compareQuestionNumbers] の自然順キーの材料。
List<String> _tokenizeForNaturalSort(String value) {
  final tokens = <String>[];
  final buffer = StringBuffer();
  bool? previousWasDigit;
  for (final unit in value.codeUnits) {
    final isDigit = unit >= 0x30 && unit <= 0x39; // '0'..'9'
    if (previousWasDigit != null && isDigit != previousWasDigit) {
      tokens.add(buffer.toString());
      buffer.clear();
    }
    buffer.writeCharCode(unit);
    previousWasDigit = isDigit;
  }
  if (buffer.isNotEmpty) tokens.add(buffer.toString());
  return tokens;
}

/// Orders question numbers the way a reviewer expects: naturally (1, 2,
/// ..., 10), not lexicographically (which would put "10" before "2"), and
/// with a single, transitive rule for labels that mix digits and letters
/// (e.g. sub-questions like "1a") -- `Question.number` accepts any non-empty
/// string (Issue #21 P2 review), so a comparator that only special-cases
/// pure-integer labels and otherwise falls back to raw string comparison is
/// not a total order (it can report `2 < 10`, `10 < "1a"`, and `"1a" < 2` all
/// at once, since "10" vs "1a" and "1a" vs "2" each take the *other* branch of
/// that special case). Comparing token-by-token with one fixed rule throughout
/// (equal-type tokens compare within their type; a numeric token always
/// sorts before a non-numeric one at the same position) avoids that: every
/// pairwise comparison normalizes both sides identically, which is what
/// makes the result transitive.
int compareQuestionNumbers(String a, String b) {
  final tokensA = _tokenizeForNaturalSort(a);
  final tokensB = _tokenizeForNaturalSort(b);
  final sharedLength = tokensA.length < tokensB.length
      ? tokensA.length
      : tokensB.length;
  for (var i = 0; i < sharedLength; i++) {
    final numA = int.tryParse(tokensA[i]);
    final numB = int.tryParse(tokensB[i]);
    if (numA != null && numB != null) {
      final comparison = numA.compareTo(numB);
      if (comparison != 0) return comparison;
      continue;
    }
    if (numA != null) return -1;
    if (numB != null) return 1;
    final comparison = tokensA[i].compareTo(tokensB[i]);
    if (comparison != 0) return comparison;
  }
  return tokensA.length.compareTo(tokensB.length);
}

/// [questions] を「答案を上から読む順」に並べた新しいリスト。
///
/// ページが先、同じページの中では設問番号の自然順。紙をめくる順であって、
/// サイドカーが返した順ではない -- 返る順は保証されていない。
List<QuestionResponse> sortQuestionsForReview(
  Iterable<QuestionResponse> questions,
) => questions.toList()
  ..sort((a, b) {
    final byPage = a.page.compareTo(b.page);
    return byPage != 0 ? byPage : compareQuestionNumbers(a.number, b.number);
  });
