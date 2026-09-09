import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/features/home/home_dashboard.dart';

/// ホーム画面が「次に何をすればいいか」をどう決めているか (Issue #68).
///
/// 画面を立ち上げずにここで検査するのは、この優先順位がホームで唯一の
/// 意見らしい意見だからである。ウィジェットの中に埋めると、順序を変えた
/// つもりが無いのに変わってしまっても誰も気付かない。
void main() {
  TestResponse buildTest({
    required String id,
    String name = 'テスト',
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

  HomeDashboard build(Map<TestResponse, List<SubmissionResponse>> work) =>
      HomeDashboard.from(
        tests: work.keys.toList(),
        submissionsByTestId: {
          for (final entry in work.entries) entry.key.id: entry.value,
        },
      );

  group('HomeWorkBucket', () {
    test('答案の7状態をホームが数える5つへ畳む', () {
      expect(HomeWorkBucket.of('needs_review'), HomeWorkBucket.needsReview);
      expect(HomeWorkBucket.of('ai_processed'), HomeWorkBucket.intakeDone);
      expect(HomeWorkBucket.of('unprocessed'), HomeWorkBucket.processing);
      expect(HomeWorkBucket.of('ai_processing'), HomeWorkBucket.processing);
      expect(HomeWorkBucket.of('error'), HomeWorkBucket.failed);
      expect(HomeWorkBucket.of('reviewed'), HomeWorkBucket.done);
      expect(HomeWorkBucket.of('exported'), HomeWorkBucket.done);
    });

    test('知らない状態は完了ではなく処理中に倒す', () {
      // サイドカーが先に新しい状態を覚えた場合、それを [done] に数えると
      // 進捗バーが「終わった」と嘘をつく。
      expect(HomeWorkBucket.of('something_new'), HomeWorkBucket.processing);
    });
  });

  group('HomeTestProgress', () {
    test('確認済みの分母は取り込んだ答案の総数', () {
      final test = buildTest(id: 't1');
      final progress = HomeTestProgress(
        test: test,
        submissions: [
          buildSubmission(id: 's1', testId: 't1', state: 'reviewed'),
          buildSubmission(id: 's2', testId: 't1', state: 'exported'),
          buildSubmission(id: 's3', testId: 't1', state: 'needs_review'),
          buildSubmission(id: 's4', testId: 't1', state: 'ai_processing'),
        ],
      );

      expect(progress.total, 4);
      expect(progress.doneCount, 2);
      expect(progress.countOf(HomeWorkBucket.needsReview), 1);
      expect(progress.countOf(HomeWorkBucket.processing), 1);
      expect(progress.countOf(HomeWorkBucket.failed), 0);
    });

    test('人が確認し終えた答案だけが確認済みに数えられ、続きからも外れる', () {
      // Issue #112 受入2・3、およびオーナー条件5。
      //
      // 進捗バーが数えるのは**講師が自分で見終えた数**であって、AIがどこまで
      // 動いたかではない。`ai_processed` は「取込と回答欄の抽出が終わった」
      // だけの状態なので (docs/home-dashboard.md §3.1)、分子に入れてはならない。
      //
      // #112 より前は、全問承認しても答案は `ai_processed` のままだったので
      // 分子が動かず、しかも `_pickResumable` がその答案をまた「続き」として
      // 差し出していた。講師には40枚のどれを見たのか分からなかった。
      final progress = HomeTestProgress(
        test: buildTest(id: 't1'),
        submissions: [
          buildSubmission(
            id: 'done',
            testId: 't1',
            state: 'reviewed',
            createdDay: 1,
          ),
          buildSubmission(
            id: 'not-done',
            testId: 't1',
            state: 'ai_processed',
            createdDay: 2,
          ),
        ],
      );

      expect(progress.doneCount, 1);
      expect(progress.countOf(HomeWorkBucket.intakeDone), 1);
      // 見終えた答案は、取込がより古くても「続き」に選ばれない。
      expect(progress.resumableSubmission?.id, 'not-done');
    });

    test('続きの1件は要確認を優先し、同じ状態なら取込の古い順', () {
      final progress = HomeTestProgress(
        test: buildTest(id: 't1'),
        submissions: [
          buildSubmission(
            id: 'old-processed',
            testId: 't1',
            state: 'ai_processed',
            createdDay: 1,
          ),
          buildSubmission(
            id: 'new-flagged',
            testId: 't1',
            state: 'needs_review',
            createdDay: 5,
          ),
          buildSubmission(
            id: 'old-flagged',
            testId: 't1',
            state: 'needs_review',
            createdDay: 3,
          ),
        ],
      );

      expect(progress.resumableSubmission?.id, 'old-flagged');
    });

    test('人間待ちが無ければ続きの1件も無い', () {
      final progress = HomeTestProgress(
        test: buildTest(id: 't1'),
        submissions: [
          buildSubmission(id: 's1', testId: 't1', state: 'ai_processing'),
          buildSubmission(id: 's2', testId: 't1', state: 'exported'),
        ],
      );

      expect(progress.resumableSubmission, isNull);
      expect(progress.order, HomeTestProgress.settledOrder);
    });
  });

  group('表示順', () {
    test('レビューが止まっているテストが先、その中では新しい順', () {
      final idle = buildTest(id: 'idle', createdDay: 9);
      final waiting = buildTest(id: 'waiting', createdDay: 2);
      final alsoWaiting = buildTest(id: 'also-waiting', createdDay: 5);

      final dashboard = build({
        idle: [buildSubmission(id: 's1', testId: 'idle', state: 'exported')],
        waiting: [
          buildSubmission(id: 's2', testId: 'waiting', state: 'needs_review'),
        ],
        alsoWaiting: [
          buildSubmission(
            id: 's3',
            testId: 'also-waiting',
            state: 'needs_review',
          ),
        ],
      });

      expect(dashboard.tests.map((t) => t.test.id), [
        'also-waiting',
        'waiting',
        'idle',
      ]);
    });
    test('新しい下書きでも、レビューが止まっているテストより後ろ', () {
      // 「次の一手」がレビューを指しているのに、その下の1枚目が下書きだと
      // 目の動きが噛み合わない。並びは nextAction の優先順位に合わせる。
      final draft = buildTest(id: 'draft', status: 'draft', createdDay: 9);
      final waiting = buildTest(id: 'waiting', createdDay: 1);
      final failed = buildTest(id: 'failed', createdDay: 5);

      final dashboard = build({
        draft: const [],
        waiting: [
          buildSubmission(id: 's1', testId: 'waiting', state: 'needs_review'),
        ],
        failed: [buildSubmission(id: 's2', testId: 'failed', state: 'error')],
      });

      expect(dashboard.tests.map((t) => t.test.id), [
        'waiting',
        'draft',
        'failed',
      ]);
    });
  });

  group('カードの絞り込み (Issue #151)', () {
    test('手が要るテストは、上限を超えていてもカードに残る', () {
      // 実機で起きたのはこれである。11教科のうち2教科が「新しい順に8件」から
      // 溢れ、そのうち古漢の要確認1件はホームのどこにも出なかった。
      //
      // 溢れる側を**古い**日付にしてあるのが要点。新しさで切る実装なら、この
      // 3件が真っ先に落ちる。
      final flagged = [
        for (var index = 0; index < 3; index++)
          buildTest(id: 'flagged-$index', createdDay: index + 1),
      ];
      final settled = [
        for (var index = 0; index < 9; index++)
          buildTest(id: 'settled-$index', createdDay: index + 10),
      ];
      final dashboard = build({
        for (final test in flagged)
          test: [
            buildSubmission(
              id: 's-${test.id}',
              testId: test.id,
              state: 'needs_review',
            ),
          ],
        for (final test in settled)
          test: [
            buildSubmission(
              id: 's-${test.id}',
              testId: test.id,
              state: 'exported',
            ),
          ],
      });

      // まず、絞り込みが実際に効いていること。全12件が載るなら、下の
      // 「要確認が残る」は何も言っていないことになる。
      expect(dashboard.tests, hasLength(12));
      expect(dashboard.visibleTests, hasLength(HomeDashboard.maxTests));
      expect(dashboard.hiddenTestCount, 12 - HomeDashboard.maxTests);

      final visibleIds = dashboard.visibleTests.map((t) => t.test.id).toList();
      expect(visibleIds, containsAll(flagged.map((t) => t.id)));

      // 落ちたのは、ホームから開く答案が無いテストだけである。
      final hidden = dashboard.tests.skip(dashboard.visibleTests.length);
      expect(hidden, isNotEmpty);
      expect(
        hidden.map((t) => t.order),
        everyElement(HomeTestProgress.settledOrder),
      );
    });

    test('手が要るテストが上限を超えたら、譲るのは上限のほう', () {
      // 上限の値を大きくするだけでは同じ事故が再発する。**カードの本数を
      // 守ることより、手が要るテストを見せることが優先される。**
      final flagged = [
        for (var index = 0; index < HomeDashboard.maxTests + 2; index++)
          buildTest(id: 'flagged-$index', createdDay: index + 1),
      ];
      final dashboard = build({
        for (final test in flagged)
          test: [
            buildSubmission(
              id: 's-${test.id}',
              testId: test.id,
              state: 'needs_review',
            ),
          ],
        buildTest(id: 'settled', createdDay: 99): [
          buildSubmission(
            id: 's-settled',
            testId: 'settled',
            state: 'exported',
          ),
        ],
      });

      expect(dashboard.visibleTests, hasLength(HomeDashboard.maxTests + 2));
      expect(
        dashboard.visibleTests.map((t) => t.test.id),
        containsAll(flagged.map((t) => t.id)),
      );
      expect(dashboard.hiddenTestCount, 1);
    });

    test('カードに載らなかったテストの答案も、件数に入る', () {
      // **これが一番静かな壊れ方である。** カードが出ないことは見れば分かるが、
      // 帯の数字が3件足りないことは誰にも見えない。
      //
      // 処理中の答案しか持たないテストは [HomeTestProgress.settledOrder] --
      // ホームから開く候補が無いのでカードの尾から落ちる。**落ちても数には
      // 残らなければならない。**
      final settled = [
        for (var index = 0; index < HomeDashboard.maxTests; index++)
          buildTest(id: 'settled-$index', createdDay: index + 10),
      ];
      final processing = [
        for (var index = 0; index < 3; index++)
          buildTest(id: 'processing-$index', createdDay: index + 1),
      ];
      final dashboard = build({
        for (final test in settled)
          test: [
            buildSubmission(
              id: 's-${test.id}',
              testId: test.id,
              state: 'exported',
            ),
          ],
        for (final test in processing)
          test: [
            buildSubmission(
              id: 's-${test.id}',
              testId: test.id,
              state: 'ai_processing',
            ),
          ],
      });

      // 先に、3件が本当にカードから落ちていること。載っているなら、下の
      // 件数は「見えているものを数えた」だけで通ってしまう。
      expect(dashboard.visibleTests, hasLength(HomeDashboard.maxTests));
      expect(dashboard.hiddenTestCount, 3);
      final visibleIds = dashboard.visibleTests.map((t) => t.test.id).toSet();
      expect(
        visibleIds.intersection(processing.map((t) => t.id).toSet()),
        isEmpty,
      );

      expect(dashboard.count(HomeWorkBucket.processing), 3);
      expect(dashboard.nextAction.headline, '処理中の答案が3件あります');
    });

    test('テストが上限以下なら、1件も隠さない', () {
      final tests = [
        for (var index = 0; index < HomeDashboard.maxTests; index++)
          buildTest(id: 't$index', createdDay: index + 1),
      ];
      final dashboard = build({for (final test in tests) test: const []});

      expect(dashboard.visibleTests, hasLength(HomeDashboard.maxTests));
      expect(dashboard.hiddenTestCount, 0);
    });
  });

  group('次の一手', () {
    test('要確認があれば、その最古の答案の添削レビューへ', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [
          buildSubmission(
            id: 'newer',
            testId: 't1',
            state: 'needs_review',
            createdDay: 4,
          ),
          buildSubmission(
            id: 'oldest',
            testId: 't1',
            state: 'needs_review',
            createdDay: 2,
          ),
        ],
      });

      final action = dashboard.nextAction;
      expect(action.headline, contains('要確認'));
      expect(action.headline, contains('2件'));
      expect(
        action.route,
        AppRoutes.pdfReview(testId: 't1', submissionId: 'oldest'),
      );
    });

    test('古いテストの要確認が、新しいテストの通常レビューより先', () {
      // テストの新しさで先にタイブレークすると、新しい方の「取込済み」が
      // 勝ってしまう。優先順位は答案のbucketが先 (§2.1)。
      final older = buildTest(id: 'older', createdDay: 1);
      final newer = buildTest(id: 'newer', createdDay: 9);
      final dashboard = build({
        newer: [
          buildSubmission(
            id: 'awaiting',
            testId: 'newer',
            state: 'ai_processed',
          ),
        ],
        older: [
          buildSubmission(
            id: 'flagged',
            testId: 'older',
            state: 'needs_review',
          ),
        ],
      });

      final action = dashboard.nextAction;
      expect(action.headline, contains('要確認'));
      expect(
        action.route,
        AppRoutes.pdfReview(testId: 'older', submissionId: 'flagged'),
      );
      // カードの並びも同じ順序でないと、上のボタンと1枚目が食い違う。
      expect(dashboard.tests.map((t) => t.test.id), ['older', 'newer']);
    });

    test('見出しは名指ししたbucketだけを数え、残りは説明文が引き取る', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [
          buildSubmission(id: 'flagged', testId: 't1', state: 'needs_review'),
          for (var index = 0; index < 9; index++)
            buildSubmission(
              id: 'awaiting-$index',
              testId: 't1',
              state: 'ai_processed',
            ),
        ],
      });

      final action = dashboard.nextAction;
      // 「要確認の答案が10件あります」だと、カードが示す 要確認 1件 と食い違う。
      expect(action.headline, '要確認の答案が1件あります');
      expect(action.detail, contains('ほかに取込済みが9件'));
    });

    test('要確認だけのときは説明文に但し書きを付けない', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [
          buildSubmission(id: 'flagged', testId: 't1', state: 'needs_review'),
        ],
      });

      expect(dashboard.nextAction.detail, isNot(contains('ほかに')));
    });

    test('取込済みの答案について、採点もレビューもどこまで進んだか断定しない', () {
      // `ai_processed` は取込時の画像前処理・回答欄抽出まで終わった状態で、
      // OCR/AI採点はその先から始まる (backend の submission_intake.py)。
      //
      // ホームが知らないのは「終わったか」だけではない。**始まったかどうかも
      // 知らない**: 起票が409や通信断で失敗した答案と、Issue #80 より前に
      // 取り込まれた答案は `ai_processed` のままジョブ0件で止まっていて、
      // ホームは `listJobs` を引かないのでそれを見分けられない
      // (docs/home-dashboard.md §3.1、review round 1 P2-1)。
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'ai_processed')],
      });

      final detail = dashboard.nextAction.detail;
      expect(detail, contains('取込と回答欄の抽出は終わっています'));
      expect(detail, contains('AI採点とレビューがどこまで進んだかはホームでは分かりません'));
      // 「開始済み」も「採点済み」も、ホームは知らない。
      expect(detail, isNot(contains('開始済み')));
      expect(detail, isNot(contains('採点済みです')));
      expect(detail, isNot(contains('採点中')));
      expect(dashboard.nextAction.headline, isNot(contains('採点済み')));
      // 「待ち」とも言わない。
      //
      // **理由は Issue #112 で1つ減った**が、無くなってはいない。かつては
      // 「承認済みの答案も `ai_processed` のままここに残る」ことが理由の1つ
      // だった (review round 2, P3)。#112 で全問確定した答案は `reviewed` へ
      // 動くようになったので、その1件は当てはまらなくなった。
      //
      // それでもこの bucket には、起票されていない答案・実行待ち・AI処理中・
      // `usable=false`・失敗/中止が残る (docs/home-dashboard.md §3.1)。
      // **どれも「待っていれば済む」とは限らない**ので、ラベルは「取込済み」の
      // ままである。
      expect(HomeWorkBucket.intakeDone.label, '取込済み');
      expect(dashboard.nextAction.headline, isNot(contains('レビュー待ち')));
    });

    test('答案が1件も無いときも、採点が必ず始まるとは言わない', () {
      // 回答欄が揃わなければ要確認で止まり、起票そのものが失敗することもある。
      final test = buildTest(id: 't1');
      final dashboard = build({test: const []});

      final detail = dashboard.nextAction.detail;
      expect(detail, contains('問題がなければ'));
      expect(detail, isNot(contains('AI採点の開始まで自動で行われます')));
    });

    test('要確認が無く取込済みだけならそちらを開く', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'ai_processed')],
      });

      final action = dashboard.nextAction;
      expect(action.headline, contains('取込済み'));
      expect(
        action.route,
        AppRoutes.pdfReview(testId: 't1', submissionId: 's1'),
      );
    });

    test('レビューすべき答案が無くなってから取込失敗を出す', () {
      final withError = buildTest(id: 't1', name: '国語 第1回');
      final dashboard = build({
        withError: [
          buildSubmission(id: 's1', testId: 't1', state: 'error'),
          buildSubmission(id: 's2', testId: 't1', state: 'exported'),
        ],
      });

      final action = dashboard.nextAction;
      expect(action.headline, contains('取込に失敗'));
      expect(action.detail, contains('国語 第1回'));
      expect(action.route, AppRoutes.intake);
    });

    test('取込失敗があっても取込済みが先', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [
          buildSubmission(id: 's1', testId: 't1', state: 'error'),
          buildSubmission(id: 's2', testId: 't1', state: 'needs_review'),
        ],
      });

      expect(dashboard.nextAction.headline, contains('要確認'));
    });

    test('登録が途中のテストはテスト設定画面へ', () {
      final draft = buildTest(id: 't1', name: '数学 第2回', status: 'draft');
      final dashboard = build({draft: const []});

      final action = dashboard.nextAction;
      expect(action.headline, contains('登録が途中'));
      expect(action.detail, contains('数学 第2回'));
      expect(action.route, AppRoutes.testSettings('t1'));
    });

    test('AI処理中しか無いときは行き先を持たず、更新だけを促す', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [
          buildSubmission(id: 's1', testId: 't1', state: 'ai_processing'),
          buildSubmission(id: 's2', testId: 't1', state: 'unprocessed'),
        ],
      });

      final action = dashboard.nextAction;
      expect(action.headline, contains('2件'));
      expect(action.route, isNull);
    });

    test('片付いていれば次の取込を促す', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'exported')],
      });

      expect(dashboard.nextAction.route, AppRoutes.intake);
    });

    test('カードに載らないテストがあっても、範囲の但し書きを付けない', () {
      // 答案は全テストぶん読んである (Issue #151)。以前はここが
      // 「直近N件のテストに、いま開く答案はありません」で、数えていない
      // テストの不在を断定しないための但し書きだった。**数えていないテストが
      // 無くなったので、但し書きも消える。**
      final settled = [
        for (var index = 0; index < HomeDashboard.maxTests + 4; index++)
          buildTest(id: 't$index', createdDay: index + 1),
      ];
      final dashboard = build({
        for (final test in settled)
          test: [
            buildSubmission(
              id: 's-${test.id}',
              testId: test.id,
              state: 'exported',
            ),
          ],
      });

      // 先に、この構成が実際に「カードから溢れている」ことを言う。溢れて
      // いなければ、下の否定形は何も検査しない。
      expect(dashboard.hiddenTestCount, 4);

      final action = dashboard.nextAction;
      expect(action.headline, 'いま開く答案はありません');
      expect(action.detail, isNot(contains('数えていません')));
      expect(action.detail, isNot(contains('数えたのは')));
    });

    test('件数に範囲の但し書きを付けない', () {
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'needs_review')],
      });

      expect(dashboard.nextAction.headline, contains('1件'));
      expect(dashboard.nextAction.detail, isNot(contains('数えたのは')));
    });

    test('取込失敗からの復旧を保証しない', () {
      // 再取込が受け付けられるのは下流データ (認識・採点・レビュー・ジョブ) が
      // 無い答案だけで、あるものは409で拒否される。ホームは下流の有無を
      // 取得していないので「取り込み直せば直る」とは言えない。
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'error')],
      });

      final action = dashboard.nextAction;
      expect(action.detail, isNot(contains('やり直せます')));
      expect(action.detail, isNot(contains('取り込み直す')));
    });

    test('処理中の行き先を1つに決めつけない', () {
      // 取込の結果は ai_processed / needs_review / error の3通りある。
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'ai_processing')],
      });

      final detail = dashboard.nextAction.detail;
      expect(detail, contains('要確認'));
      expect(detail, contains('取込失敗'));
    });

    test('取込済みの答案の順序を、テストをまたいだ最古と読ませない', () {
      // 実際の選択は「テストを選んでから、その中で取込の古い順」。
      final test = buildTest(id: 't1');
      final dashboard = build({
        test: [buildSubmission(id: 's1', testId: 't1', state: 'ai_processed')],
      });

      expect(dashboard.nextAction.detail, contains('テストごとに'));
    });

    test('下書きのどの確認手順が残っているかは断定しない', () {
      // `ready` にはプロファイルと依存関係グラフ両方の確定が要るが、どちらが
      // 済んでいるかはホームが取得していない。
      final draft = buildTest(id: 't1', name: '理科 第1回', status: 'draft');
      final dashboard = build({draft: const []});

      expect(dashboard.nextAction.detail, contains('登録がまだ完了していません'));
      expect(dashboard.nextAction.detail, isNot(contains('終わっていません')));
    });

    test('テストが1件も無ければテスト登録へ', () {
      final dashboard = build(const {});

      expect(dashboard.isEmpty, isTrue);
      expect(dashboard.nextAction.route, AppRoutes.intake);
    });
  });
}
