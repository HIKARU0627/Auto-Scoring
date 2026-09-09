import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/features/home/home_page.dart';
import 'package:auto_scoring_app/features/review_queue/submission_queue_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_list_page.dart';

import 'app_harness.dart';

/// 答案キュー画面 (Issue #113)。
///
/// 40枚を続けてさばくとき、**いま何枚あって、どれが済んでいて、次はどれか**が
/// この画面から読めなければならない。
void main() {
  TestResponse buildTest({String name = '国語 第1回'}) => TestResponse(
    (b) => b
      ..id = 't1'
      ..name = name
      ..status = 'ready'
      ..createdAt = DateTime.utc(2026, 1, 1),
  );

  SubmissionResponse buildSubmission({
    required String id,
    required String state,
    int day = 1,
    String? studentLabel,
    String? reviewReason,
  }) => SubmissionResponse(
    (b) => b
      ..id = id
      ..testId = 't1'
      ..state = state
      ..pageCount = 1
      ..studentLabel = studentLabel
      ..reviewReason = reviewReason
      ..createdAt = DateTime.utc(2026, 2, day),
  );

  SubmissionReviewProgressResponse buildProgress({
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

  AppDependencies deps({
    required List<SubmissionResponse> submissions,
    List<SubmissionReviewProgressResponse> progress = const [],
    Future<List<SubmissionReviewProgressResponse>> Function(String)?
    listReviewProgress,
  }) => AppDependencies(
    getTest: (_) async => buildTest(),
    listSubmissions: (_) async => submissions,
    listReviewProgress: listReviewProgress ?? (_) async => progress,
  );

  testWidgets('済んだ答案も含めて全件出る', (tester) async {
    // 絞り込んで隠さない。残りの中身を読み分ける手がかりごと消すことになる。
    await pumpAppAt(
      tester,
      AppRoutes.submissionQueue('t1'),
      dependencies: deps(
        submissions: [
          buildSubmission(id: 'done', state: 'reviewed', studentLabel: '答案A'),
          buildSubmission(
            id: 'todo',
            state: 'ai_processed',
            day: 2,
            studentLabel: '答案B',
          ),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('queue-row-done')), findsOneWidget);
    expect(find.byKey(const Key('queue-row-todo')), findsOneWidget);
    expect(find.text('確認済み 1 / 2'), findsOneWidget);
  });

  testWidgets('行から状態が読める', (tester) async {
    await pumpAppAt(
      tester,
      AppRoutes.submissionQueue('t1'),
      dependencies: deps(
        submissions: [
          buildSubmission(
            id: 'flagged',
            state: 'needs_review',
            studentLabel: '答案A',
            reviewReason: 'answer_area_undefined:q-2',
          ),
        ],
      ),
    );
    await tester.pumpAndSettle();

    // ラベルは `SubmissionStatusVisual` のもの。この画面が独自の語を作らない。
    expect(find.text('要確認'), findsOneWidget);
    // 取込が何を見つけたのかを出す。「要確認」だけでは何を見ればいいか分からない。
    // **ただし生のワイヤ形式は出さない** -- `answer_area_undefined:q-2` は
    // 講師に読ませるものではない (Issue #122 の `submission_review_reason.dart`)。
    expect(find.text('回答欄が確定できない設問が1問あります'), findsOneWidget);
    expect(find.textContaining('answer_area_undefined'), findsNothing);
  });

  testWidgets('知らない理由には何も言わない', (tester) async {
    // 新しいサイドカーがこのビルドの知らない旗を立てたとき、当てずっぽうの
    // ラベルを付けると実際とは違うことを講師に読ませることになる。
    await pumpAppAt(
      tester,
      AppRoutes.submissionQueue('t1'),
      dependencies: deps(
        submissions: [
          buildSubmission(
            id: 'odd',
            state: 'needs_review',
            studentLabel: '答案A',
            reviewReason: 'something_new_we_do_not_know:q-1',
          ),
        ],
      ),
    );
    await tester.pumpAndSettle();

    // 状態ラベルは出る。理由の行は出ない。
    expect(find.text('要確認'), findsOneWidget);
    expect(find.textContaining('something_new'), findsNothing);
    expect(find.textContaining('あります'), findsNothing);
  });

  testWidgets('途中まで確定した答案が、手つかずと区別できる', (tester) async {
    // 答案の state が動くのは全設問が確定したときだけ (Issue #112)。設問粒度の
    // 数が無いと、3/5 の答案は未着手と同じ見た目になり、中断して戻ってきた
    // 講師には「どこまでやったか」が読めない。
    await pumpAppAt(
      tester,
      AppRoutes.submissionQueue('t1'),
      dependencies: deps(
        submissions: [
          buildSubmission(
            id: 'half',
            state: 'ai_processed',
            studentLabel: '答案A',
          ),
        ],
        progress: [buildProgress(id: 'half', confirmed: 3)],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('3 / 5 問 確定'), findsOneWidget);
  });

  testWidgets('AIが採点できなかった答案は、そうと分かる', (tester) async {
    // その答案だけは、AIの提案を確認するのではなく自分で点数を入れる必要がある
    // (Issue #118 の「点数を入力」)。残り3枚が「見るだけ」なのか「1問ずつ採点」
    // なのかで、残り時間の見積もりがまるで違う。
    await pumpAppAt(
      tester,
      AppRoutes.submissionQueue('t1'),
      dependencies: deps(
        submissions: [
          buildSubmission(
            id: 'stuck',
            state: 'ai_processed',
            studentLabel: '答案A',
          ),
          buildSubmission(
            id: 'fine',
            state: 'ai_processed',
            day: 2,
            studentLabel: '答案B',
          ),
        ],
        progress: [
          buildProgress(id: 'stuck', manualGrading: 1),
          buildProgress(id: 'fine'),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('queue-manual-grade-stuck')), findsOneWidget);
    expect(find.byKey(const Key('queue-manual-grade-fine')), findsNothing);
  });

  testWidgets('行をタップするとその答案の添削レビューへ行く', (tester) async {
    await pumpAppAt(
      tester,
      AppRoutes.submissionQueue('t1'),
      dependencies: deps(
        submissions: [
          buildSubmission(id: 's1', state: 'ai_processed', studentLabel: '答案A'),
        ],
      ),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('queue-row-s1')));
    // 遷移のアニメーションを進める。`pumpAndSettle` は使わない -- 添削レビュー
    // 画面はサイドカーを待って回り続けるので、落ち着くのを待つと返ってこない。
    await tester.pump();
    await tester.pump(const Duration(seconds: 1));

    // 添削レビュー画面はサイドカーを引くので描き切らない。確かめたいのは
    // **その答案の**レビューが開いたことなので、ルータが付ける key を見る
    // (`app_router.dart`: 答案ごとに別の `State` にするためのもの)。
    // 「キューが見えなくなったこと」では、push の途中でも通ってしまう。
    expect(find.byKey(const ValueKey('pdf-review/t1/s1')), findsOneWidget);
  });

  testWidgets('答案が1件も無いときは、そう言う', (tester) async {
    await pumpAppAt(
      tester,
      AppRoutes.submissionQueue('t1'),
      dependencies: deps(submissions: const []),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('queue-empty')), findsOneWidget);
  });

  testWidgets('進捗が引けなくても一覧は出る', (tester) async {
    // 数が出ないのは、一覧が出ないより軽い。
    await pumpAppAt(
      tester,
      AppRoutes.submissionQueue('t1'),
      dependencies: deps(
        submissions: [
          buildSubmission(id: 's1', state: 'ai_processed', studentLabel: '答案A'),
        ],
        listReviewProgress: (_) async => throw SidecarApiException(
          SidecarErrorKind.unavailable,
          'progress unavailable',
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('queue-row-s1')), findsOneWidget);
    expect(find.byKey(const Key('queue-error')), findsNothing);
    // 数だけが消える。
    expect(find.byKey(const Key('queue-progress-s1')), findsNothing);
  });

  testWidgets('一覧そのものが引けなければ、エラーと再読み込みを出す', (tester) async {
    await pumpAppAt(
      tester,
      AppRoutes.submissionQueue('t1'),
      dependencies: AppDependencies(
        getTest: (_) async => buildTest(),
        listSubmissions: (_) async => throw SidecarApiException(
          SidecarErrorKind.unavailable,
          'サイドカーに接続できません',
        ),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('queue-error')), findsOneWidget);
    expect(find.text('再読み込み'), findsOneWidget);
  });

  group('PDF出力 (Issue #137)', () {
    // 全問承認した答案はホームの「レビューを続ける」から消える (Issue #112)。
    // #113 でこの一覧から開き直せるようになったが、**出力ボタンは添削レビュー
    // 画面にしか無かった**ので、成果物である採点済みPDFへ到達するには
    // 一覧 -> レビュー画面 と2枚めくる必要があった。ここはその近道である。

    testWidgets('確定し終えた答案の行から、レビュー画面を開かずに出力できる', (tester) async {
      var requestedFor = <String>[];
      await pumpAppAt(
        tester,
        AppRoutes.submissionQueue('t1'),
        dependencies: AppDependencies(
          getTest: (_) async => buildTest(),
          listSubmissions: (_) async => [
            buildSubmission(id: 'done', state: 'reviewed', studentLabel: '答案A'),
          ],
          listReviewProgress: (_) async => [
            buildProgress(id: 'done', total: 3, confirmed: 3),
          ],
          requestExport: (submissionId) async {
            requestedFor.add(submissionId);
            // `reuse_existing` -- ジョブを起票せずに既存の出力を返す枝。
            // ポーリングを回さずに済むので、ここで見たい「押すと出力が始まる」
            // だけを見られる。
            return ExportRequestResponse(
              (b) => b
                ..decision = 'reuse_existing'
                ..export_ = ExportResponse(
                  (e) => e
                    ..id = 'export-1'
                    ..submissionId = submissionId
                    ..jobId = 'job-1'
                    ..filePath = 'exports/答案A_corrected.pdf'
                    ..fileSha256 = 'a' * 64
                    ..createdAt = DateTime.utc(2026, 3, 1),
                ).toBuilder(),
            );
          },
        ),
      );
      await tester.pumpAndSettle();

      // **先に画面が描けていることを言う。** これが無いと、以下の
      // `findsOneWidget` は「行が1つも無い」ときに何も守らない。
      expect(find.byKey(const Key('queue-row-done')), findsOneWidget);

      final exportButton = find.byKey(const Key('queue-export-done'));
      expect(exportButton, findsOneWidget);

      await tester.tap(exportButton);
      await tester.pumpAndSettle();

      // 出力が始まり、行から開いた添削レビュー画面はどこにも出ていない。
      expect(requestedFor, ['done']);
      expect(find.byKey(const Key('export-dialog-success')), findsOneWidget);
      expect(find.text('保存先: exports/答案A_corrected.pdf'), findsOneWidget);
      // 添削レビュー画面へは行っていない。出力はこの一覧の上で完結する。
      expect(find.text('添削レビュー'), findsNothing);
      expect(find.text('答案キュー'), findsOneWidget);
    });

    testWidgets('状態が動いていなくても、全問確定していれば出力できる', (tester) async {
      // Issue #112 より前に採点し終えた答案は、全設問が確定したまま
      // `ai_processed` に残っている (遡って直すマイグレーションは無い)。
      // サイドカーはこれを出力するので、**画面が状態を見て隠してはいけない**。
      await pumpAppAt(
        tester,
        AppRoutes.submissionQueue('t1'),
        dependencies: deps(
          submissions: [
            buildSubmission(
              id: 'legacy',
              state: 'ai_processed',
              studentLabel: '答案B',
            ),
          ],
          progress: [buildProgress(id: 'legacy', total: 3, confirmed: 3)],
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('queue-row-legacy')), findsOneWidget);
      expect(find.byKey(const Key('queue-export-legacy')), findsOneWidget);
    });

    testWidgets('確定していない答案には出力を出さない', (tester) async {
      // 押しても必ず 409 で断られるボタンは、出さないほうがよい。開く導線
      // (`onTap`) は残っているので、行き止まりにはならない。
      await pumpAppAt(
        tester,
        AppRoutes.submissionQueue('t1'),
        dependencies: deps(
          submissions: [
            buildSubmission(id: 'half', state: 'ai_processed', day: 2),
          ],
          progress: [buildProgress(id: 'half', total: 5, confirmed: 4)],
        ),
      );
      await tester.pumpAndSettle();

      // **行が描けていることを先に言う。** これが無ければ次の findsNothing は
      // 画面が真っ白でも通る。
      expect(find.byKey(const Key('queue-row-half')), findsOneWidget);
      expect(find.byKey(const Key('queue-progress-half')), findsOneWidget);
      expect(find.byKey(const Key('queue-export-half')), findsNothing);
    });

    testWidgets('進捗が引けなかった答案には出力を出さない', (tester) async {
      // 0 / 0 を「全部確定した」と読むと、確認済みの答案にすら押せないボタンが
      // 並ぶ。分からないときは出さない。
      await pumpAppAt(
        tester,
        AppRoutes.submissionQueue('t1'),
        dependencies: deps(
          submissions: [
            buildSubmission(id: 'done', state: 'reviewed', studentLabel: '答案A'),
          ],
          listReviewProgress: (_) async => throw SidecarApiException(
            SidecarErrorKind.unavailable,
            '進捗を取得できません',
          ),
        ),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('queue-row-done')), findsOneWidget);
      expect(find.byKey(const Key('queue-export-done')), findsNothing);
    });
  });

  group('入口が違っても、同じように戻れる (Issue #160)', () {
    // **この画面には入口が3つある。** ホームのテストカード、テスト一覧、そして
    // 添削レビューの「答案キューへ」(`docs/review-queue.md` §8)。実機再検証 #5
    // では3つ目だけがアプリバーの戻る矢印を出さず、Escape も Alt+Left も効かず、
    // **アプリを再起動するまでホームへ戻れなかった**。
    //
    // 3つ目 (スナックバー) の分は添削レビュー画面を組み立てないと再現しないので
    // `pdf_review_page_test.dart` の「Issue #113」グループにある。入口を増やした
    // ときに検査が抜けるのを止めるのは `navigation_stack_lint_test.dart`。

    /// ホームとテスト一覧の両方から入れるだけの、1テスト・1答案の構成。
    AppDependencies entryDeps() => AppDependencies(
      listTestRegistrations: () async => [buildTest()],
      getTest: (_) async => buildTest(),
      listSubmissions: (_) async => [
        buildSubmission(id: 'todo', state: 'ai_processed', studentLabel: '答案A'),
      ],
      listReviewProgress: (_) async => [buildProgress(id: 'todo')],
    );

    testWidgets('ホームのテストカードから入っても、ホームへ戻れる', (tester) async {
      await pumpAppAt(tester, AppRoutes.home, dependencies: entryDeps());
      await tester.pumpAndSettle();

      // 押す対象が本当に出ていること。これを言わずに進むと、タップが空振り
      // したときに「戻れた」ではなく「まだホームに居る」で緑になる。
      expect(find.byKey(const Key('home-open-queue-t1')), findsOneWidget);

      await tester.tap(find.byKey(const Key('home-open-queue-t1')));
      await tester.pumpAndSettle();

      expect(find.byType(SubmissionQueuePage), findsOneWidget);
      expect(find.byType(BackButton), findsOneWidget);

      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();

      expect(find.byType(HomePage), findsOneWidget);
    });

    testWidgets('テスト一覧から入っても、テスト一覧へ戻れる', (tester) async {
      await pumpAppAt(tester, AppRoutes.testList, dependencies: entryDeps());
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('test-list-tile-t1')), findsOneWidget);

      await tester.tap(find.byKey(const Key('test-list-tile-t1')));
      await tester.pumpAndSettle();

      expect(find.byType(SubmissionQueuePage), findsOneWidget);
      expect(find.byType(BackButton), findsOneWidget);

      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();

      expect(find.byType(TestListPage), findsOneWidget);
    });
  });
}
