import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/review_queue.dart';

/// 答案キューの並び順と現在地 (Issue #113)。
///
/// 画面を立ち上げずにここで検査するのは `home_dashboard_test.dart` と同じ理由で、
/// **並び順はこのアプリで最も意見の入る部分**だからである。ウィジェットの中に
/// 埋めると、順序を変えたつもりが無いのに変わっても誰も気付かない。
void main() {
  SubmissionResponse sub({
    required String id,
    required String state,
    int day = 1,
  }) => SubmissionResponse(
    (b) => b
      ..id = id
      ..testId = 't1'
      ..state = state
      ..pageCount = 1
      ..createdAt = DateTime.utc(2026, 2, day),
  );

  SubmissionReviewProgressResponse progress({
    required String id,
    int total = 5,
    int confirmed = 0,
    int manualGrading = 0,
  }) => SubmissionReviewProgressResponse(
    (b) => b
      ..submissionId = id
      ..totalQuestions = total
      ..confirmedQuestions = confirmed
      ..manualGradingQuestions = manualGrading,
  );

  group('並び順', () {
    test('要確認が先、同じ状態なら取込の古い順', () {
      // ホーム画面の「レビューを続ける」が選ぶ1件と、キューの先頭は一致して
      // いなければならない。違う答案が開いたら、講師はどちらも信用できなくなる。
      final queue = ReviewQueue.from(
        submissions: [
          sub(id: 'old-processed', state: 'ai_processed', day: 1),
          sub(id: 'new-flagged', state: 'needs_review', day: 5),
          sub(id: 'old-flagged', state: 'needs_review', day: 3),
        ],
      );

      expect(queue.entries.map((e) => e.id), [
        'old-flagged',
        'new-flagged',
        'old-processed',
      ]);
      expect(queue.first?.id, 'old-flagged');
    });

    test('済んだ答案も一覧からは消えない', () {
      // 絞り込んで隠さない。全件見えることが、残りの中身を読み分ける前提になる
      // (docs/review-queue.md の出典)。
      final queue = ReviewQueue.from(
        submissions: [
          sub(id: 'done', state: 'reviewed', day: 1),
          sub(id: 'todo', state: 'ai_processed', day: 2),
        ],
      );

      expect(queue.entries.map((e) => e.id), containsAll(['done', 'todo']));
      expect(queue.total, 2);
      expect(queue.doneCount, 1);
    });
  });

  group('現在地', () {
    test('positionOf は1始まりで、表示順と一致する', () {
      final queue = ReviewQueue.from(
        submissions: [
          sub(id: 'a', state: 'ai_processed', day: 1),
          sub(id: 'b', state: 'ai_processed', day: 2),
        ],
      );

      expect(queue.positionOf('a'), 1);
      expect(queue.positionOf('b'), 2);
      // 知らない答案を0にするのは、「1枚目」と紛れさせないため。
      expect(queue.positionOf('no-such'), 0);
    });
  });

  group('次の1件', () {
    test('済んだ答案は飛ばす', () {
      // 一覧に出すことと、もう一度開かせることは別である。
      final queue = ReviewQueue.from(
        submissions: [
          sub(id: 'a', state: 'ai_processed', day: 1),
          sub(id: 'b', state: 'reviewed', day: 2),
          sub(id: 'c', state: 'ai_processed', day: 3),
        ],
      );

      expect(queue.nextAfter('a')?.id, 'c');
    });

    test('末尾まで済んでいれば、前に残っている未了へ戻る', () {
      // 「後回し (S)」で送った答案はキューの手前に残る。これが無いと拾えない。
      final queue = ReviewQueue.from(
        submissions: [
          sub(id: 'deferred', state: 'ai_processed', day: 1),
          sub(id: 'current', state: 'ai_processed', day: 2),
        ],
      );

      expect(queue.nextAfter('current')?.id, 'deferred');
    });

    test('未了が自分しか無ければ次は無い', () {
      final queue = ReviewQueue.from(
        submissions: [
          sub(id: 'done', state: 'reviewed', day: 1),
          sub(id: 'current', state: 'ai_processed', day: 2),
        ],
      );

      expect(queue.nextAfter('current'), isNull);
    });

    test('全部済んでいれば first も次も無い', () {
      final queue = ReviewQueue.from(
        submissions: [sub(id: 'done', state: 'reviewed', day: 1)],
      );

      expect(queue.first, isNull);
      expect(queue.nextAfter('done'), isNull);
    });
  });

  group('設問粒度の進捗', () {
    test('途中まで確定した答案が、手つかずと区別できる', () {
      // 答案の state が動くのは全設問が確定したときだけ (Issue #112) なので、
      // これが無いと 3/5 の答案は未着手と同じ見た目になる。中断して戻った講師に
      // 「どこまでやったか」が読めない。
      final queue = ReviewQueue.from(
        submissions: [
          sub(id: 'half', state: 'ai_processed', day: 1),
          sub(id: 'untouched', state: 'ai_processed', day: 2),
        ],
        progress: [
          progress(id: 'half', confirmed: 3),
          progress(id: 'untouched'),
        ],
      );

      expect(queue.entryFor('half')!.isPartiallyReviewed, isTrue);
      expect(queue.entryFor('half')!.confirmedQuestions, 3);
      expect(queue.entryFor('untouched')!.isPartiallyReviewed, isFalse);
    });

    test('AIが採点できなかった答案は、手を動かす量が違うと分かる', () {
      // ほかの答案はAIの提案を確認するだけだが、これは1問ずつ自分で点数を入れる
      // (Issue #118 の「点数を入力」)。残り3枚が「見るだけ」なのか「自分で採点」
      // なのかで、金曜の午後の残り時間の見積もりがまるで違う。
      final queue = ReviewQueue.from(
        submissions: [
          sub(id: 'stuck', state: 'ai_processed', day: 1),
          sub(id: 'fine', state: 'ai_processed', day: 2),
        ],
        progress: [
          progress(id: 'stuck', manualGrading: 1),
          progress(id: 'fine'),
        ],
      );

      expect(queue.entryFor('stuck')!.needsManualGrading, isTrue);
      expect(queue.entryFor('fine')!.needsManualGrading, isFalse);
    });

    test('進捗が取れなくても一覧は成立する', () {
      // 数が出ないのは、一覧が出ないより軽い。
      final queue = ReviewQueue.from(
        submissions: [sub(id: 'a', state: 'ai_processed', day: 1)],
      );

      expect(queue.total, 1);
      expect(queue.entryFor('a')!.totalQuestions, 0);
      expect(queue.entryFor('a')!.isPartiallyReviewed, isFalse);
    });
  });

  group('出力してよい答案 (Issue #137)', () {
    test('全設問が確定していれば、状態が reviewed でなくても出力できる', () {
      // **これが `isDone` では取りこぼす答案である。** Issue #112 より前は
      // `ai_processed` が `_REVIEWABLE_SUBMISSION_STATES` から外れていたため、
      // 普通に取り込めた答案は全問承認しても状態が動かなかった。遡って直す
      // マイグレーションは無いので、それ以前に採点し終えた答案はいまも
      // `ai_processed` のまま、全設問が確定した状態で残っている。
      //
      // サイドカーはこれを出力する (`unconfirmed_question_ids` が空)。画面が
      // 状態を見て導線を隠せば、出力できるのに出せない答案ができる -- #137 が
      // 消しに来た行き止まりそのものである。
      final queue = ReviewQueue.from(
        submissions: [sub(id: 'legacy', state: 'ai_processed', day: 1)],
        progress: [progress(id: 'legacy', total: 5, confirmed: 5)],
      );

      final entry = queue.entryFor('legacy')!;
      expect(entry.isDone, isFalse, reason: '状態は動いていない');
      expect(entry.isFullyConfirmed, isTrue, reason: 'それでも全問確定している');
    });

    test('確認済みの答案はもちろん出力できる', () {
      final queue = ReviewQueue.from(
        submissions: [sub(id: 'done', state: 'reviewed', day: 1)],
        progress: [progress(id: 'done', total: 3, confirmed: 3)],
      );

      expect(queue.entryFor('done')!.isFullyConfirmed, isTrue);
    });

    test('1問でも残っていれば出力できない', () {
      final queue = ReviewQueue.from(
        submissions: [sub(id: 'half', state: 'ai_processed', day: 1)],
        progress: [progress(id: 'half', total: 5, confirmed: 4)],
      );

      expect(queue.entryFor('half')!.isFullyConfirmed, isFalse);
    });

    test('進捗が引けていないときは出力できると言わない', () {
      // 0 / 0 を「全部確定した」と読むと、押した先で必ず 409 になるボタンが
      // 出る。**分からないときは出さない。**
      final queue = ReviewQueue.from(
        submissions: [sub(id: 'unknown', state: 'reviewed', day: 1)],
      );

      final entry = queue.entryFor('unknown')!;
      expect(entry.totalQuestions, 0, reason: '進捗が無い状態を作れている');
      expect(entry.isFullyConfirmed, isFalse);
    });
  });
}
