import 'dart:io';

import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/submission_confirmation.dart';

/// 答案1枚を1回で確定してよいかの判定 (Issue #145)。
///
/// **ウィジェットを1つも立てずに読む。** 確定してよいかはこのアプリで最も
/// 間違えたくない判断で、スクロールを再現しないと確かめられない形にすると、
/// 誰も網羅しなくなる (`core/review_queue.dart` と同じ理由)。
void main() {
  QuestionConfirmation question({
    String id = 'q-1',
    String number = '1',
    bool materialLoaded = true,
    bool isConfirmed = false,
    String? aiGradeId = 'grade-1',
    int expectedVersion = 0,
    bool isReached = true,
  }) => QuestionConfirmation(
    questionId: id,
    number: number,
    materialLoaded: materialLoaded,
    isConfirmed: isConfirmed,
    aiGradeId: aiGradeId,
    expectedVersion: expectedVersion,
    isReached: isReached,
  );

  group('確定してよいか', () {
    test('全設問に到達していれば確定できる', () {
      final confirmation = SubmissionConfirmation([
        question(id: 'q-1', number: '1'),
        question(id: 'q-2', number: '2'),
      ]);

      expect(confirmation.blocker, isNull);
      expect(confirmation.canConfirm, isTrue);
      expect(confirmation.pending.length, 2);
    });

    test('未到達の設問が1つでもあれば確定できず、それがどれか分かる', () {
      final confirmation = SubmissionConfirmation([
        question(id: 'q-1', number: '1'),
        question(id: 'q-2', number: '2', isReached: false),
        question(id: 'q-3', number: '3'),
        question(id: 'q-4', number: '4', isReached: false),
      ]);

      expect(confirmation.canConfirm, isFalse);
      expect(confirmation.blocker, SubmissionConfirmBlock.unreached);
      // **名前が要る。** 「どこかを見ていません」では画面を探させることになる。
      expect(confirmation.unreached.map((q) => q.number), ['2', '4']);
    });

    test('確定済みの設問には到達を求めない', () {
      // もう一度見せろと言うことになるが、その確定は過去に人が見て決めたもので
      // あって、この画面がやり直させるものではない。
      final confirmation = SubmissionConfirmation([
        question(id: 'q-1', number: '1', isConfirmed: true, isReached: false),
        question(id: 'q-2', number: '2'),
      ]);

      expect(confirmation.canConfirm, isTrue);
      expect(confirmation.unreached, isEmpty);
      expect(confirmation.pending.map((q) => q.number), ['2']);
      expect(confirmation.confirmedCount, 1);
    });

    test('AIが採点できなかった設問があると、到達していても確定できない', () {
      // `Review.APPROVED` は `ai_grade_result_id` を要求するので、この設問は
      // 承認しようがない。到達したところでその事実は消えない。
      final confirmation = SubmissionConfirmation([
        question(id: 'q-1', number: '1'),
        question(id: 'q-2', number: '2', aiGradeId: null),
      ]);

      expect(confirmation.canConfirm, isFalse);
      expect(confirmation.blocker, SubmissionConfirmBlock.humanScoreRequired);
      expect(confirmation.needingHumanScore.map((q) => q.number), ['2']);
    });

    test('読み込めていない設問があれば、それが最初の理由になる', () {
      // 出ていないものについて「見ましたか」と訊いても答えようがない。
      final confirmation = SubmissionConfirmation([
        question(id: 'q-1', number: '1', materialLoaded: false),
        question(id: 'q-2', number: '2', isReached: false),
      ]);

      expect(confirmation.blocker, SubmissionConfirmBlock.materialUnavailable);
      expect(confirmation.unloaded.map((q) => q.number), ['1']);
    });

    test('全部確定済みなら、確定するものが無いと言う', () {
      final confirmation = SubmissionConfirmation([
        question(id: 'q-1', number: '1', isConfirmed: true),
        question(id: 'q-2', number: '2', isConfirmed: true),
      ]);

      expect(confirmation.blocker, SubmissionConfirmBlock.nothingToConfirm);
      expect(confirmation.isFullyConfirmed, isTrue);
    });

    test('設問が無い答案は確定できない', () {
      const confirmation = SubmissionConfirmation([]);

      expect(confirmation.blocker, SubmissionConfirmBlock.noQuestions);
      expect(confirmation.isFullyConfirmed, isFalse);
    });
  });

  group('N回の確定を流す', () {
    test('全部通れば、確定した設問が順に並ぶ', () async {
      final calls = <String>[];
      final outcome = await runSubmissionConfirmation(
        questions: [
          question(id: 'q-1', number: '1'),
          question(id: 'q-2', number: '2'),
          question(id: 'q-3', number: '3'),
        ],
        approve: (q) async => calls.add(q.questionId),
      );

      expect(calls, ['q-1', 'q-2', 'q-3']);
      expect(outcome.isComplete, isTrue);
      expect(outcome.confirmed, ['1', '2', '3']);
      expect(outcome.remaining, isEmpty);
    });

    test('3問目で失敗したら、そこまでを数え、残りを名指しで返す', () async {
      // schema を変えない以上、答案1枚の確定は設問ごとのAPIをN回呼ぶ形にしか
      // ならず、**途中で失敗しうる**。「確定できませんでした」とだけ言う画面は、
      // 2問確定した事実を人から隠す。
      final calls = <String>[];
      final outcome = await runSubmissionConfirmation(
        questions: [
          question(id: 'q-1', number: '1'),
          question(id: 'q-2', number: '2'),
          question(id: 'q-3', number: '3'),
          question(id: 'q-4', number: '4'),
        ],
        approve: (q) async {
          calls.add(q.questionId);
          if (q.questionId == 'q-3') {
            throw SidecarApiException(SidecarErrorKind.conflict, '他の操作と競合しました');
          }
        },
      );

      // **最初の失敗で止める。** 押し通しても失敗が並ぶだけである。
      expect(calls, ['q-1', 'q-2', 'q-3']);
      expect(outcome.isComplete, isFalse);
      expect(outcome.confirmed, ['1', '2']);
      expect(outcome.failedNumber, '3');
      expect(outcome.message, contains('競合'));
      expect(outcome.remaining, ['3', '4']);
    });

    test('1問目で失敗しても、残りは全部残っていると言う', () async {
      final outcome = await runSubmissionConfirmation(
        questions: [
          question(id: 'q-1', number: '1'),
          question(id: 'q-2', number: '2'),
        ],
        approve: (q) async => throw SidecarApiException(
          SidecarErrorKind.unavailable,
          'サイドカーに接続できません',
        ),
      );

      expect(outcome.confirmed, isEmpty);
      expect(outcome.remaining, ['1', '2']);
      expect(outcome.failedNumber, '1');
    });

    test('確定する設問が無ければ、1回も呼ばない', () async {
      var calls = 0;
      final outcome = await runSubmissionConfirmation(
        questions: const [],
        approve: (q) async => calls++,
      );

      expect(calls, 0);
      expect(outcome.isComplete, isTrue);
      expect(outcome.confirmed, isEmpty);
    });
  });

  group('確信度は入力にならない', () {
    test('この判定に確信度が入り込んでいない', () {
      // 簡易設計書 §25.2「確信度から完了を導かない」。Issue #136 が実測した
      // とおり、確信度1.00の誤った0点は14件中7件あり、正しい0点と画面上で同じ
      // 顔をしていた。**閾値で選別すれば、誤りだけが選ばれて確定する。**
      //
      // 「確信度を受け取っていないこと」は値では測れない -- 引数が無いのだから、
      // どんな入力を作っても赤くならない。だから**判定を書いた場所そのもの**を
      // 読む。confidence を引数に足した瞬間に、このテストが赤くなる。
      final source = File(
        'lib/core/submission_confirmation.dart',
      ).readAsStringSync();
      // docstring では「確信度を入力にしない」と書いてあるので、識別子として
      // 現れるところだけを見る。
      final identifier = RegExp(r'\bconfidence\b', caseSensitive: false);
      final offenders = [
        for (final line in source.split('\n'))
          if (identifier.hasMatch(line) && !line.trimLeft().startsWith('///'))
            line.trim(),
      ];

      expect(
        offenders,
        isEmpty,
        reason:
            '確定の可否に確信度を入れてはならない（簡易設計書 §25.2、Issue #136）:\n'
            '${offenders.join('\n')}',
      );
    });
  });
}
