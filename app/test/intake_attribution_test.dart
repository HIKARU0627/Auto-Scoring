import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/intake_attribution.dart';
import 'package:auto_scoring_app/core/intake_review.dart';

TestSummary _test(String id) => TestSummary(
  (b) => b
    ..id = id
    ..name = 'テスト $id',
);

IntakeFileState _file(
  String path, {
  String? answerTestId,
  String? proposedAnswerTestId,
}) => IntakeFileState(
  relativePath: path,
  absolutePath: '/tmp/$path',
  sha256: '0' * 64,
  sizeBytes: 1,
  ruleRole: MaterialRole.studentAnswer,
  needsClassification: false,
  answerTestId: answerTestId,
  proposedAnswerTestId: proposedAnswerTestId,
);

void main() {
  group('attributionCandidates', () {
    final tests = [_test('t1'), _test('t2'), _test('t3')];

    test('絞り込みが無ければ登録済み全部が候補', () {
      expect(
        attributionCandidates(existingTests: tests, narrowedTestIds: const {}),
        tests,
      );
    });

    test('絞り込むと候補もそれだけになる', () {
      final candidates = attributionCandidates(
        existingTests: tests,
        narrowedTestIds: {'t2'},
      );
      expect(candidates.map((t) => t.id), ['t2']);
    });

    test('絞り込んだ id が消えたテストは候補から落ちる', () {
      // The selection can outlive the list it points into -- the registered
      // tests are re-read at the start of every batch.
      final candidates = attributionCandidates(
        existingTests: tests,
        narrowedTestIds: {'gone'},
      );
      expect(candidates, isEmpty);
    });
  });

  group('reviewerChoseOneTest', () {
    test('1件に絞り、候補も1件なら選んだとみなす', () {
      expect(
        reviewerChoseOneTest(narrowedTestIds: {'t1'}, candidateCount: 1),
        isTrue,
      );
    });

    test('絞り込みが無く候補がたまたま1件でも選んだとはみなさない', () {
      // A count of one can mean "the reviewer said so" or "only one test
      // happens to be registered" -- treating them the same would assign
      // every answer with nobody having chosen anything.
      expect(
        reviewerChoseOneTest(narrowedTestIds: const {}, candidateCount: 1),
        isFalse,
      );
    });

    test('絞り込んだテストが消えて候補が0件になったら選んだとはみなさない', () {
      expect(
        reviewerChoseOneTest(narrowedTestIds: {'gone'}, candidateCount: 0),
        isFalse,
      );
    });
  });

  group('dropRoutingOutsideCandidates', () {
    test('候補に無いテストへのルーティングと提案を消す', () {
      final review = IntakeReviewState(
        groups: [
          IntakeGroupState(
            key: 'g1',
            name: '国語',
            requiredRoles: const [],
            targetKind: IntakeTargetKind.perAnswer,
            files: [
              _file('a.pdf', answerTestId: 't1', proposedAnswerTestId: 't1'),
              _file('b.pdf', proposedAnswerTestId: 't2'),
            ],
          ),
        ],
      );

      final result = dropRoutingOutsideCandidates(review, {'t2'});

      final a = result.allFiles.firstWhere((f) => f.relativePath == 'a.pdf');
      expect(a.answerTestId, isNull);
      expect(a.proposedAnswerTestId, isNull);
      final b = result.allFiles.firstWhere((f) => f.relativePath == 'b.pdf');
      expect(b.proposedAnswerTestId, 't2');
    });

    test('候補に残っているルーティングはそのまま', () {
      final review = IntakeReviewState(
        groups: [
          IntakeGroupState(
            key: 'g1',
            name: '国語',
            requiredRoles: const [],
            targetKind: IntakeTargetKind.perAnswer,
            files: [_file('a.pdf', answerTestId: 't1')],
          ),
        ],
      );

      final result = dropRoutingOutsideCandidates(review, {'t1'});

      expect(result.allFiles.single.answerTestId, 't1');
    });
  });
}
