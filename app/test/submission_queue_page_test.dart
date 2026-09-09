import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';

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
    int failed = 0,
  }) => SubmissionReviewProgressResponse(
    (b) => b
      ..submissionId = id
      ..totalQuestions = total
      ..confirmedQuestions = confirmed
      ..failedQuestions = failed,
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
    expect(find.text('answer_area_undefined:q-2'), findsOneWidget);
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

  testWidgets('AI採点が失敗した答案は、そうと分かる', (tester) async {
    // 「自分が後回しにした答案」と「AIが失敗して手が出ない答案」は読み分けられ
    // なければならない。前者は自分で戻ってくるが、後者は放っておくと永久に
    // 終わらない (Issue #118)。
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
          buildProgress(id: 'stuck', failed: 1),
          buildProgress(id: 'fine'),
        ],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('queue-stuck-stuck')), findsOneWidget);
    expect(find.byKey(const Key('queue-stuck-fine')), findsNothing);
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
}
