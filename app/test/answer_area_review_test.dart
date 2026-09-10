import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/answer_area_review.dart';

RegionModel _answerArea(String label) => RegionModel(
  (b) => b
    ..regionId = 'r-$label'
    ..kind = RegionKind.answerArea
    ..pageIndex = 0
    ..label = label
    ..confirmed = false
    ..bbox.x0 = 0.1
    ..bbox.y0 = 0.1
    ..bbox.x1 = 0.3
    ..bbox.y1 = 0.2,
);

RegionModel _question(String label) => RegionModel(
  (b) => b
    ..regionId = 'q-$label'
    ..kind = RegionKind.question
    ..pageIndex = 0
    ..label = label
    ..confirmed = false
    ..bbox.x0 = 0.1
    ..bbox.y0 = 0.1
    ..bbox.x1 = 0.3
    ..bbox.y1 = 0.2,
);

void main() {
  group('missingAnswerAreas', () {
    test('回答欄がある設問はどちらにも入らない', () {
      final result = missingAnswerAreas(
        regions: [_answerArea('問1')],
        questionNumbers: const ['問1'],
        reportedAbsent: const {},
      );

      expect(result.undetected, isEmpty);
      expect(result.absent, isEmpty);
    });

    test('サーバが absent と報告した設問は absent に入る', () {
      final result = missingAnswerAreas(
        regions: const [],
        questionNumbers: const ['問1', '問2'],
        reportedAbsent: const {'問1'},
      );

      expect(result.absent, ['問1']);
      expect(result.undetected, ['問2']);
    });

    test('回答欄を手で引くと absent からも undetected からも外れる', () {
      // The membership test reads the *working* copy, not the last server
      // response -- otherwise a box the reviewer just drew would keep
      // showing as missing until the next round trip.
      final result = missingAnswerAreas(
        regions: [_answerArea('問1')],
        questionNumbers: const ['問1'],
        reportedAbsent: const {'問1'},
      );

      expect(result.absent, isEmpty);
      expect(result.undetected, isEmpty);
    });
  });

  group('unassignedAnswerAreas', () {
    test('確定済み設問の番号を持つ回答欄は含まない', () {
      final unassigned = unassignedAnswerAreas(
        regions: [_answerArea('問1')],
        knownQuestionNumbers: {'問1'},
      );

      expect(unassigned, isEmpty);
    });

    test('確定済み設問に無い番号の回答欄を返す', () {
      final region = _answerArea('問9');
      final unassigned = unassignedAnswerAreas(
        regions: [region],
        knownQuestionNumbers: {'問1'},
      );

      expect(unassigned, [region]);
    });

    test('回答欄以外の領域（問題文など）は対象外', () {
      final unassigned = unassignedAnswerAreas(
        regions: [_question('問9')],
        knownQuestionNumbers: {'問1'},
      );

      expect(unassigned, isEmpty);
    });
  });

  group('mustSeeAnswerSheetFirst', () {
    test('答案が表示できていて回答欄があれば確定できる', () {
      expect(
        mustSeeAnswerSheetFirst(
          answerSheetVisible: true,
          regions: [_answerArea('問1')],
        ),
        isFalse,
      );
    });

    test('答案が表示できていなくても回答欄が無ければブロックしない', () {
      // No answer area means nothing is being attested to sit at a
      // particular place on a page nobody has seen yet.
      expect(
        mustSeeAnswerSheetFirst(answerSheetVisible: false, regions: const []),
        isFalse,
      );
    });

    test('答案が表示できていないのに回答欄があればブロックする', () {
      expect(
        mustSeeAnswerSheetFirst(
          answerSheetVisible: false,
          regions: [_answerArea('問1')],
        ),
        isTrue,
      );
    });
  });
}
