import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/features/home/home_dashboard.dart';
import 'package:auto_scoring_app/features/pdf_review/pdf_review_page.dart';
import 'package:auto_scoring_app/features/review_queue/submission_queue_page.dart';
import 'package:auto_scoring_app/features/intake/intake_page.dart';
import 'package:auto_scoring_app/features/test_registration/test_settings_page.dart';

import 'app_harness.dart';

/// ホーム画面 (Issue #68).
///
/// 受入条件のうち画面側の3つ -- 起動直後に進行中の作業と次の行動が分かる、
/// デバッグ表示が無い、中断した作業へ直接復帰できる -- をここで検査する。
/// 優先順位そのものは `home_dashboard_test.dart`。
void main() {
  TestResponse buildTest({
    required String id,
    String name = '国語 第1回',
    String status = 'ready',
    int createdDay = 1,
  }) => TestResponse(
    (b) => b
      ..id = id
      ..name = name
      ..status = status
      ..createdAt = DateTime.utc(2026, 1, createdDay),
  );

  SubmissionResponse buildSubmission({
    required String id,
    required String testId,
    required String state,
    int createdDay = 1,
    String? studentLabel,
  }) => SubmissionResponse(
    (b) => b
      ..id = id
      ..testId = testId
      ..state = state
      ..pageCount = 1
      ..studentLabel = studentLabel
      ..createdAt = DateTime.utc(2026, 2, createdDay),
  );

  AppDependencies dependenciesFor(
    Map<TestResponse, List<SubmissionResponse>> work,
  ) => AppDependencies(
    listTestRegistrations: () async => work.keys.toList(),
    listSubmissions: (testId) async =>
        work.entries.firstWhere((entry) => entry.key.id == testId).value,
  );

  testWidgets('起動確認用のデバッグ表示は残っていない', (tester) async {
    await pumpAppAt(
      tester,
      AppRoutes.home,
      dependencies: dependenciesFor({buildTest(id: 't1'): const []}),
    );
    await tester.pumpAndSettle();

    // `backend: ok` はサイドカーの生存確認で、それは Issue #24 の
    // スプラッシュ/エラー画面の仕事。ここへ戻ってくると二重に持つことになる。
    expect(find.textContaining('backend'), findsNothing);
  });

  testWidgets('進行中の作業の内訳と、テストごとの進み具合が出る', (tester) async {
    final test = buildTest(id: 't1', name: '国語 第1回');
    await pumpAppAt(
      tester,
      AppRoutes.home,
      dependencies: dependenciesFor({
        test: [
          buildSubmission(id: 's1', testId: 't1', state: 'needs_review'),
          buildSubmission(id: 's2', testId: 't1', state: 'ai_processing'),
          buildSubmission(id: 's3', testId: 't1', state: 'error'),
          buildSubmission(id: 's4', testId: 't1', state: 'reviewed'),
          buildSubmission(id: 's5', testId: 't1', state: 'exported'),
        ],
      }),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-test-card-t1')), findsOneWidget);
    expect(find.text('国語 第1回'), findsOneWidget);
    // 達成感の側: 分母は取り込んだ答案の総数。
    expect(find.text('確認済み 2 / 5'), findsOneWidget);
    // 進行中の側: 0件のものは並べない。
    expect(find.text('要確認 1件'), findsOneWidget);
    expect(find.text('処理中 1件'), findsOneWidget);
    expect(find.text('取込失敗 1件'), findsOneWidget);
    expect(find.text('取込済み 0件'), findsNothing);
    // 確認済みは進捗バーが担当していて、数字を二度書かない。
    expect(find.textContaining('確認済み 2件'), findsNothing);
  });

  testWidgets('次の一手から、中断した答案の添削レビューへ直接戻れる', (tester) async {
    final test = buildTest(id: 't1');
    await pumpAppAt(
      tester,
      AppRoutes.home,
      dependencies: dependenciesFor({
        test: [
          buildSubmission(
            id: 'newer',
            testId: 't1',
            state: 'needs_review',
            createdDay: 5,
          ),
          buildSubmission(
            id: 'oldest',
            testId: 't1',
            state: 'needs_review',
            createdDay: 2,
          ),
        ],
      }),
    );
    await tester.pumpAndSettle();

    expect(find.text('要確認の答案が2件あります'), findsOneWidget);
    await tester.tap(find.byKey(const Key('home-next-up-action')));
    await tester.pumpAndSettle();

    final page = tester.widget<PdfReviewPage>(find.byType(PdfReviewPage));
    expect(page.testId, 't1');
    expect(page.submissionId, 'oldest');
  });

  testWidgets('テストカードからも、そのテストの続きの答案へ戻れる', (tester) async {
    final busy = buildTest(id: 'busy', name: '数学 第2回', createdDay: 2);
    final idle = buildTest(id: 'idle', name: '英語 第3回', createdDay: 9);
    await pumpAppAt(
      tester,
      AppRoutes.home,
      dependencies: dependenciesFor({
        idle: [buildSubmission(id: 'done', testId: 'idle', state: 'exported')],
        busy: [
          buildSubmission(
            id: 'open',
            testId: 'busy',
            state: 'needs_review',
            studentLabel: '答案A',
          ),
        ],
      }),
    );
    await tester.pumpAndSettle();

    // 人間待ちのテストが先に並ぶので、片付いているテストにレビュー導線は無い。
    expect(find.byKey(const Key('home-resume-review-idle')), findsNothing);
    expect(find.text('レビューを続ける（答案A）'), findsOneWidget);

    await tester.tap(find.byKey(const Key('home-resume-review-busy')));
    await tester.pumpAndSettle();

    final page = tester.widget<PdfReviewPage>(find.byType(PdfReviewPage));
    expect(page.submissionId, 'open');
  });

  testWidgets('確認済みの数を押すと、そのテストの答案キューへ行ける', (tester) async {
    // **答案キューへの入口はここだけである** (Issue #113)。これが無いと、
    // 一覧は作ってあるのに誰もたどり着けない。
    //
    // ボタンを増やさず、既に出ている「確認済み N / M」を押せるようにしてある。
    // #68 でホームの情報量を絞ったのは正しかったが、**あのときは答案キューが
    // 存在しなかった**。
    final test = buildTest(id: 't1', name: '国語 第1回');
    await pumpAppAt(
      tester,
      AppRoutes.home,
      dependencies: dependenciesFor({
        test: [
          buildSubmission(id: 'done', testId: 't1', state: 'reviewed'),
          buildSubmission(id: 'todo', testId: 't1', state: 'ai_processed'),
        ],
      }),
    );
    await tester.pumpAndSettle();

    // 押す前に、押す対象が本当に出ていることを言う。これが無いと、画面が
    // 描けていなくても後続の findsNothing 系が通ってしまう。
    expect(find.text('確認済み 1 / 2'), findsOneWidget);

    await tester.tap(find.byKey(const Key('home-open-queue-t1')));
    await tester.pumpAndSettle();

    final page = tester.widget<SubmissionQueuePage>(
      find.byType(SubmissionQueuePage),
    );
    expect(page.testId, 't1');
  });

  testWidgets('登録が途中のテストはテスト設定画面へ戻す', (tester) async {
    final draft = buildTest(id: 't1', name: '理科 第1回', status: 'draft');
    await pumpAppAt(
      tester,
      AppRoutes.home,
      dependencies: dependenciesFor({draft: const []}),
    );
    await tester.pumpAndSettle();

    expect(find.text('登録が途中のテストがあります'), findsOneWidget);
    await tester.tap(find.byKey(const Key('home-resume-registration-t1')));
    await tester.pumpAndSettle();

    final page = tester.widget<TestSettingsPage>(find.byType(TestSettingsPage));
    expect(page.testId, 't1');
  });

  testWidgets('テストが1件も無ければ、まずテスト登録へ導く', (tester) async {
    await pumpAppAt(
      tester,
      AppRoutes.home,
      dependencies: dependenciesFor(const {}),
    );
    await tester.pumpAndSettle();

    expect(find.text('まだテストが登録されていません'), findsOneWidget);

    // Issue #95 決定 1 で模範解答PDFは廃止した。実在しない資料なので、画面が
    // それを要求すると利用者は用意できないものを探すことになる (オーナーが実機で
    // 指摘した最初の問題がこれ)。この文言は Issue #101 が入力を作り直したあとも
    // main に残っていたので、ここで固定する。
    expect(
      find.textContaining('模範解答'),
      findsNothing,
      reason: '模範解答PDFは廃止された。画面が要求してはいけない',
    );
    expect(
      find.textContaining('採点マニュアル'),
      findsNothing,
      reason: '「採点マニュアルPDF」は旧仕様の呼び名。いまは採点基準PDF',
    );

    await tester.tap(find.byKey(const Key('home-next-up-action')));
    await tester.pumpAndSettle();

    expect(find.byType(IntakePage), findsOneWidget);
  });

  testWidgets('AI処理中しか無いときは、押せるのが更新だけになる', (tester) async {
    var loads = 0;
    final test = buildTest(id: 't1');
    final dependencies = AppDependencies(
      listTestRegistrations: () async {
        loads++;
        return [test];
      },
      listSubmissions: (_) async => [
        buildSubmission(id: 's1', testId: 't1', state: 'ai_processing'),
      ],
    );
    await pumpAppAt(tester, AppRoutes.home, dependencies: dependencies);
    await tester.pumpAndSettle();

    expect(loads, 1);
    await tester.tap(find.byKey(const Key('home-next-up-action')));
    await tester.pumpAndSettle();

    // 画面はそのまま。数え直しただけ。
    expect(loads, 2);
    expect(find.text('処理中の答案が1件あります'), findsOneWidget);
  });

  testWidgets('載せきれなかったテストの件数を隠さない', (tester) async {
    final tests = [
      for (var index = 0; index < HomeDashboard.maxTests + 3; index++)
        buildTest(id: 't$index', name: 'テスト$index', createdDay: index + 1),
    ];
    await pumpAppAt(
      tester,
      AppRoutes.home,
      dependencies: AppDependencies(
        listTestRegistrations: () async => tests,
        listSubmissions: (_) async => const [],
      ),
    );
    await tester.pumpAndSettle();

    expect(find.text('他3件を見る'), findsOneWidget);
    // どれも答案が無く、順位が並ぶので、残るのは新しい順に上限ぶん。
    expect(
      find.byKey(Key('home-test-card-t${HomeDashboard.maxTests + 2}')),
      findsOneWidget,
    );
    expect(find.byKey(const Key('home-test-card-t0')), findsNothing);
  });

  testWidgets('溢れたテストの要確認が、カードにも帯にも出る (Issue #151)', (tester) async {
    // 実機再検証 #4 の再現。11教科を登録し、**溢れた2教科にだけ**要確認がある。
    // 以前のホームは `createdAt` の新しい順に8件だけ答案を読んでいたので、
    // この2教科はカードに出ず、しかも「要確認が2件あります」の数にも
    // 入らなかった -- 利用者から見ると仕事が残っていないように見える。
    //
    // 溢れる側を**いちばん古い**日付にしてある。1件だけだと順序のあやで
    // たまたま拾えてしまうので、2件にしてある (実機で溢れたのも2教科)。
    const flaggedNames = ['化学', '古漢'];
    final flagged = [
      for (final (index, name) in flaggedNames.indexed)
        buildTest(id: 'flagged-$index', name: name, createdDay: index + 1),
    ];
    final settled = [
      for (var index = 0; index < 9; index++)
        buildTest(
          id: 'settled-$index',
          name: 'テスト$index',
          createdDay: index + 10,
        ),
    ];
    final fetched = <String>[];
    await pumpAppAt(
      tester,
      AppRoutes.home,
      dependencies: AppDependencies(
        listTestRegistrations: () async => [...settled, ...flagged],
        listSubmissions: (testId) async {
          fetched.add(testId);
          return testId.startsWith('flagged-')
              ? [
                  buildSubmission(
                    id: 's-$testId',
                    testId: testId,
                    state: 'needs_review',
                  ),
                ]
              : [
                  buildSubmission(
                    id: 's-$testId',
                    testId: testId,
                    state: 'exported',
                  ),
                ];
        },
      ),
    );
    await tester.pumpAndSettle();

    // 溢れた2教科の答案を、そもそも読みに行っていること。ここが8件で
    // 打ち切られていたのが原因なので、最初に押さえる。
    expect(fetched, containsAll(flagged.map((test) => test.id)));

    // カードに出る。
    for (final test in flagged) {
      expect(
        find.byKey(Key('home-test-card-${test.id}')),
        findsOneWidget,
        reason: '${test.name} のカードが出ていない',
      );
    }
    // 出ているのは上限ぶんで、押し出されたのは片付いたテストのほう。
    expect(find.text('他3件を見る'), findsOneWidget);

    // 帯の数字が2件を数えている。**カードが出ないことは見れば分かるが、
    // 数字が足りないことは誰にも見えない。**
    expect(find.text('要確認の答案が2件あります'), findsOneWidget);
  });

  testWidgets('取得に失敗したら、その旨と再試行を出す', (tester) async {
    var attempts = 0;
    final dependencies = AppDependencies(
      listTestRegistrations: () async {
        attempts++;
        if (attempts == 1) {
          throw SidecarApiException(
            SidecarErrorKind.unavailable,
            'sidecar is not connected',
          );
        }
        return [buildTest(id: 't1')];
      },
      listSubmissions: (_) async => const [],
    );
    await pumpAppAt(tester, AppRoutes.home, dependencies: dependencies);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-error')), findsOneWidget);

    await tester.tap(find.text('再試行'));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('home-error')), findsNothing);
    expect(find.byKey(const Key('home-test-card-t1')), findsOneWidget);
  });
}
