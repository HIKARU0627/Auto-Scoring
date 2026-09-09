import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/criteria_totals.dart';
import 'package:flutter_test/flutter_test.dart';

/// 同じ例を `backend/tests/test_criteria_extraction.py` が固定している。
/// 片方だけ変えると、画面の合計とサーバの合計が食い違う。
CriteriaQuestionModel _question(String number, int? points) {
  return CriteriaQuestionModel(
    (b) => b
      ..number = number
      ..points = points,
  );
}

void main() {
  group('criteriaTotals', () {
    test('分かっている配点だけを足し、残りを数える', () {
      final totals = criteriaTotals([
        _question('問1', 5),
        _question('問2', null),
        _question('問3', 8),
        _question('問4', null),
      ]);

      expect(totals.knownPoints, 13);
      expect(totals.unknownCount, 2);
      expect(totals.isComplete, isFalse);
    });

    test('不明は 0 として足されない', () {
      // 不明を 0 として扱うと、この 2 つの合計が同じになってしまう。
      final withUnknown = criteriaTotals([
        _question('問1', 5),
        _question('問2', null),
      ]);
      final withZero = criteriaTotals([_question('問1', 5), _question('問2', 0)]);

      expect(withUnknown.knownPoints, withZero.knownPoints);
      expect(withUnknown.unknownCount, 1);
      expect(withZero.unknownCount, 0);
      expect(withUnknown.isComplete, isFalse);
      expect(withZero.isComplete, isTrue);
    });

    test('総得点と一致しなければ差を出す', () {
      final totals = criteriaTotals([
        _question('問1', 5),
        _question('問2', 8),
      ], declaredTotalPoints: 20);

      expect(totals.declaredDifference, 7);
    });

    test('総得点と一致すれば差は出さない', () {
      final totals = criteriaTotals([
        _question('問1', 5),
        _question('問2', 8),
      ], declaredTotalPoints: 13);

      expect(totals.declaredDifference, isNull);
    });

    test('不明が残っている間は差を出さない', () {
      // 差は未入力で既に説明がついている。別の問題として見せると、
      // 存在しない 2 つめの原因を探しに行かせてしまう。
      final totals = criteriaTotals([
        _question('問1', 5),
        _question('問2', null),
      ], declaredTotalPoints: 20);

      expect(totals.unknownCount, 1);
      expect(totals.declaredDifference, isNull);
    });

    test('空のとき', () {
      final totals = criteriaTotals(const []);
      expect(totals.knownPoints, 0);
      expect(totals.unknownCount, 0);
      expect(totals.isComplete, isTrue);
    });
  });

  group('criteriaBlockingReason', () {
    test('設問が無ければ理由を返す', () {
      expect(criteriaBlockingReason(const []), contains('1 件もありません'));
    });

    test('配点が不明なら件数つきで理由を返す', () {
      final reason = criteriaBlockingReason([
        _question('問1', 5),
        _question('問2', null),
        _question('問3', null),
      ]);
      expect(reason, contains('2 件'));
      expect(reason, contains('不明'));
    });

    test('配点が 0 以下なら理由を返す', () {
      expect(criteriaBlockingReason([_question('問1', 0)]), contains('0 以下'));
    });

    test('すべて埋まっていれば null', () {
      expect(
        criteriaBlockingReason([_question('問1', 5), _question('問2', 8)]),
        isNull,
      );
    });
  });

  group('dependencyGraphDescribesQuestions', () {
    test('設問集合が一致していれば true', () {
      expect(
        dependencyGraphDescribesQuestions(
          testId: 't1',
          graphQuestionIds: const ['t1:問1', 't1:問2'],
          criteriaNumbers: const ['問1', '問2'],
          questionRegionLabels: const [],
        ),
        isTrue,
      );
    });

    test('確定後に設問が増えていれば false（サーバは409で断る状態）', () {
      // `status == 'confirmed'` だけを見ていると、ここで「残っていることは
      // ありません」と出してしまう。
      expect(
        dependencyGraphDescribesQuestions(
          testId: 't1',
          graphQuestionIds: const ['t1:問1'],
          criteriaNumbers: const ['問1', '問2'],
          questionRegionLabels: const [],
        ),
        isFalse,
      );
    });

    test('設問が減っていても false', () {
      expect(
        dependencyGraphDescribesQuestions(
          testId: 't1',
          graphQuestionIds: const ['t1:問1', 't1:問2'],
          criteriaNumbers: const ['問1'],
          questionRegionLabels: const [],
        ),
        isFalse,
      );
    });

    test('領域だけの設問も合併して数える', () {
      // `build_questions_and_rubrics` の合併規則と同じ。
      expect(
        dependencyGraphDescribesQuestions(
          testId: 't1',
          graphQuestionIds: const ['t1:問1', 't1:問2'],
          criteriaNumbers: const ['問1'],
          questionRegionLabels: const ['問2'],
        ),
        isTrue,
      );
    });

    test('両方に出てくる設問を二重に数えない', () {
      expect(
        dependencyGraphDescribesQuestions(
          testId: 't1',
          graphQuestionIds: const ['t1:問1'],
          criteriaNumbers: const ['問1'],
          questionRegionLabels: const ['問1'],
        ),
        isTrue,
      );
    });
  });
}
