import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/question_order.dart';

/// 設問の並び順 (Issue #145 で `pdf_review_page.dart` から出したもの)。
///
/// 添削レビュー画面と答案確定画面が同じ答案の設問を並べる。**2か所で別々に
/// 並べると、確定画面の3枚目とレールの3番目が別の設問になる** -- そうなると
/// 「問3を見た」という到達の記録がどの設問についてのものか分からなくなる。
void main() {
  QuestionResponse question(String number, {int page = 1}) => QuestionResponse(
    (b) => b
      ..id = 'q-$number-p$page'
      ..testId = 'test-1'
      ..number = number
      ..page = page
      ..points = 5
      ..scoringMethod = 'additive',
  );

  test('設問番号は自然順に並ぶ', () {
    final numbers = ['10', '2', '1', '3']..sort(compareQuestionNumbers);

    // 文字列順なら "10" が "2" より前に来る。
    expect(numbers, ['1', '2', '3', '10']);
  });

  test('数字と文字が混ざっても、全順序として壊れない', () {
    // `Question.number` は空でない任意の文字列を受ける。整数だけを特別扱いして
    // 残りを文字列比較に落とすと `2 < 10`・`10 < "1a"`・`"1a" < 2` が同時に成り
    // 立ちうる（推移律が壊れ、sort の結果が入力順に依存する）。
    expect(compareQuestionNumbers('2', '10'), lessThan(0));
    expect(compareQuestionNumbers('10', '1a'), greaterThan(0));
    expect(compareQuestionNumbers('1a', '2'), lessThan(0));

    final forwards = ['2', '10', '1a']..sort(compareQuestionNumbers);
    final backwards = ['1a', '10', '2']..sort(compareQuestionNumbers);
    expect(forwards, backwards);
  });

  test('ページが先、同じページの中では設問番号', () {
    // 紙をめくる順である。サイドカーが返す順ではない。
    final sorted = sortQuestionsForReview([
      question('2', page: 2),
      question('10', page: 1),
      question('1', page: 2),
      question('2', page: 1),
    ]);

    expect(sorted.map((q) => '${q.page}-${q.number}'), [
      '1-2',
      '1-10',
      '2-1',
      '2-2',
    ]);
  });

  test('渡したリストは書き換えない', () {
    final original = [question('2'), question('1')];
    sortQuestionsForReview(original);

    expect(original.map((q) => q.number), ['2', '1']);
  });
}
