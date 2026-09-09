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
    int failed = 0,
  }) => SubmissionReviewProgressResponse(
    (b) => b
      ..submissionId = id
      ..totalQuestions = total
      ..confirmedQuestions = confirmed
      ..failedQuestions = failed,
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

    test('AI採点が失敗した答案は「詰んでいる」と分かる', () {
      // 後回しにした答案は自分で戻ってくるが、こちらは放っておくと永久に
      // 終わらない (Issue #118)。残り3枚の中身を読み分けるための区別である。
      final queue = ReviewQueue.from(
        submissions: [
          sub(id: 'stuck', state: 'ai_processed', day: 1),
          sub(id: 'fine', state: 'ai_processed', day: 2),
        ],
        progress: [
          progress(id: 'stuck', failed: 1),
          progress(id: 'fine'),
        ],
      );

      expect(queue.entryFor('stuck')!.isStuck, isTrue);
      expect(queue.entryFor('fine')!.isStuck, isFalse);
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
}
