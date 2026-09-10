import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';

import 'app_harness.dart';

/// 答案確定画面 (Issue #145)。
///
/// 確かめたいのは3つある。
///
/// 1. **未到達の設問が1つでもあれば確定できない**、そして**どれが未到達かが
///    画面に出る**。まとめて確定する画面は、Issue #85 が消した「見ないで承認」を
///    設問の数だけ作り直しうる。
/// 2. **全設問に到達したら、1回の操作で確定できる。** 200回を40回にするのが
///    この Issue である。
/// 3. **部分失敗を隠さない。** schema を変えないので確定はN回の呼び出しで、
///    途中で失敗しうる。どこまで確定したかと、残りをどうするかが出ること。
void main() {
  const testId = 'test-1';
  const submissionId = 'sub-1';

  SubmissionResponse submission({
    String state = 'ai_processed',
    String? reviewReason,
  }) => SubmissionResponse(
    (b) => b
      ..id = submissionId
      ..testId = testId
      ..state = state
      ..pageCount = 1
      ..studentLabel = '答案A'
      ..reviewReason = reviewReason
      ..createdAt = DateTime.utc(2026, 1, 1),
  );

  QuestionResponse question(String number) => QuestionResponse(
    (b) => b
      ..id = 'q-$number'
      ..testId = testId
      ..number = number
      ..page = 1
      ..points = 5
      ..scoringMethod = 'additive',
  );

  RecognitionResponse recognition(String questionId) => RecognitionResponse(
    (b) => b
      ..id = 'rec-$questionId'
      ..submissionId = submissionId
      ..questionId = questionId
      ..source_ = 'ai'
      ..stage = 'ocr'
      ..text = '$questionId の答案本文。光合成によって酸素が発生する。'
      ..confidence = 0.91
      ..createdAt = DateTime.utc(2026, 1, 1),
  );

  GradeResultResponse grade(String questionId) => GradeResultResponse(
    (b) => b
      ..id = 'grade-$questionId'
      ..submissionId = submissionId
      ..questionId = questionId
      ..source_ = 'ai'
      ..score.awarded = 4
      ..score.maximum = 5
      ..score.ratio = 0.8
      ..confidence = 0.88
      ..rationale = '理由の説明が不足しています。'
      ..createdAt = DateTime.utc(2026, 1, 1),
  );

  ReviewResponse approvedReview(String questionId) => ReviewResponse(
    (b) => b
      ..id = 'review-$questionId'
      ..submissionId = submissionId
      ..questionId = questionId
      ..action = 'approved'
      ..version = 1
      ..aiGradeResultId = 'grade-$questionId'
      ..createdAt = DateTime.utc(2026, 1, 2),
  );

  ReviewActionResponse actionResponse(String questionId) =>
      ReviewActionResponse(
        (b) => b
          ..review = approvedReview(questionId).toBuilder()
          ..annotations.replace(const <AnnotationResponse>[])
          ..submissionState = 'ai_processed',
      );

  JobResponse job(String questionId, {String state = 'succeeded'}) =>
      JobResponse(
        (b) => b
          ..id = 'job-$questionId'
          ..kind = 'grading'
          ..submissionId = submissionId
          ..questionId = questionId
          ..state = state
          ..usable = true
          ..dependencyGraphVersion = 1
          ..attempts = 1
          ..maxAttempts = 3
          ..createdAt = DateTime.utc(2026, 1, 1)
          ..updatedAt = DateTime.utc(2026, 1, 1),
      );

  /// [numbers] の設問を持つ答案1件ぶんのサイドカー。
  ///
  /// 切り出し画像は既定で 404 を返す。画像そのものはこの画面の検査対象では
  /// なく（`answer_crop_view_test.dart` が見ている）、**行の高さは画像が届いても
  /// 変わらない**ように固定してあるので、到達の測り方は 404 でも本物でも同じ
  /// 経路を通る。
  AppDependencies deps({
    List<String> numbers = const ['1', '2', '3', '4', '5'],
    Set<String> alreadyConfirmed = const {},
    Set<String> withoutAiGrade = const {},
    ApproveReview? approveReview,
    List<SubmissionResponse>? queueSubmissions,
    SubmissionResponse? submissionOverride,
    ListQuestions? listQuestions,
  }) {
    return AppDependencies(
      getSubmission: (_) async => submissionOverride ?? submission(),
      listQuestions:
          listQuestions ?? (_) async => numbers.map(question).toList(),
      listJobs: (_) async => [for (final n in numbers) job('q-$n')],
      listRecognitions: (_, questionId) async => [recognition(questionId)],
      listGrades: (_, questionId) async =>
          withoutAiGrade.contains(questionId) ? const [] : [grade(questionId)],
      listReviews: (_, questionId) async =>
          alreadyConfirmed.contains(questionId)
          ? [approvedReview(questionId)]
          : const <ReviewResponse>[],
      getAnswerImage: (_, _) async => throw SidecarApiException(
        SidecarErrorKind.badResponse,
        'not found',
        statusCode: 404,
      ),
      listSubmissions: (_) async =>
          queueSubmissions ?? <SubmissionResponse>[submission()],
      listReviewProgress: (_) async =>
          const <SubmissionReviewProgressResponse>[],
      approveReview:
          approveReview ??
          (
            _,
            questionId, {
            required expectedVersion,
            expectedAiGradeId,
            note,
          }) async => actionResponse(questionId),
    );
  }

  Future<void> pumpConfirm(
    WidgetTester tester,
    AppDependencies dependencies, {
    Size size = const Size(1280, 720),
    Brightness brightness = Brightness.light,
  }) async {
    await tester.binding.setSurfaceSize(size);
    addTearDown(() => tester.binding.setSurfaceSize(null));
    await pumpAppAt(
      tester,
      AppRoutes.submissionConfirm(testId: testId, submissionId: submissionId),
      dependencies: dependencies,
      brightness: brightness,
    );
    await tester.pumpAndSettle();
  }

  /// 判断材料を上から下まで通す -- **人がやるのと同じ、指で送る操作**である。
  ///
  /// 戻り値はスクロール操作の回数。1回の確定に何回の操作が要るかを数えるのに
  /// 使う（[操作数の測定] を参照）。
  Future<int> scrollThroughMaterial(WidgetTester tester) async {
    final list = find.byKey(const Key('confirm-question-list'));
    for (var drags = 0; drags < 40; drags++) {
      final button = tester.widget<FilledButton>(
        find.byKey(const Key('confirm-submission-button')),
      );
      if (button.onPressed != null) return drags;
      await tester.drag(list, const Offset(0, -300));
      await tester.pumpAndSettle();
    }
    return 40;
  }

  bool confirmEnabled(WidgetTester tester) =>
      tester
          .widget<FilledButton>(
            find.byKey(const Key('confirm-submission-button')),
          )
          .onPressed !=
      null;

  group('見ていないものを確定させない (Issue #85 との両立)', () {
    testWidgets('未到達の設問が残っている間は確定できない', (tester) async {
      await pumpConfirm(tester, deps());

      // 開いた直後、下のほうの設問はまだ画面に出ていない。
      expect(confirmEnabled(tester), isFalse);
      expect(
        find.byKey(const Key('confirm-blocked-unreached')),
        findsOneWidget,
      );
    });

    testWidgets('どれが未到達かが画面に出る', (tester) async {
      await pumpConfirm(tester, deps(numbers: const ['1', '2', '3']));

      final notice = tester.widget<Text>(
        find.descendant(
          of: find.byKey(const Key('confirm-blocked-unreached')),
          matching: find.byType(Text),
        ),
      );
      // 「どこかを見ていません」では、40枚を流している人に画面を探させる。
      expect(notice.data, contains('問3'));
      expect(notice.data, contains('まだ表示していない設問があります'));

      // 行の側にも出る。告知を読み飛ばしても、どの設問が未表示かは分かる。
      expect(find.byKey(const Key('confirm-reach-q-1')), findsOneWidget);
      expect(find.text('未表示'), findsWidgets);
    });

    testWidgets('狭幅 (700x720) でも同じように止まり、同じように開く', (tester) async {
      await pumpConfirm(
        tester,
        deps(numbers: const ['1', '2', '3']),
        size: const Size(700, 720),
      );

      expect(confirmEnabled(tester), isFalse);
      await scrollThroughMaterial(tester);
      expect(confirmEnabled(tester), isTrue);
      expect(tester.takeException(), isNull);
    });

    testWidgets('確定済みの設問には、もう一度の表示を求めない', (tester) async {
      // その確定は過去に人が見て決めたもので、この画面がやり直させるものでは
      // ない。**未確定の1問に届いた時点で確定できる**ことを、全問が未確定の
      // ときとの手数の差で確かめる -- 「先頭の1枚だけ見れば済む」は、5枚とも
      // 見なければ済まない場合と比べて初めて意味を持つ。
      await pumpConfirm(tester, deps());
      final dragsWhenNothingConfirmed = await scrollThroughMaterial(tester);

      await pumpConfirm(
        tester,
        deps(alreadyConfirmed: const {'q-2', 'q-3', 'q-4', 'q-5'}),
      );
      final dragsWhenOnlyFirstPending = await scrollThroughMaterial(tester);

      expect(dragsWhenOnlyFirstPending, lessThan(dragsWhenNothingConfirmed));
      expect(confirmEnabled(tester), isTrue);
      expect(find.byKey(const Key('confirm-ready-notice')), findsOneWidget);
      // 下の設問は表示していないままである -- 求めていないだけで、見たことに
      // されてはいない。
      expect(find.text('未表示'), findsWidgets);
    });
  });

  group('1回の操作で確定する', () {
    testWidgets('全設問に到達したら、1回押すだけで設問の数だけ確定が走る', (tester) async {
      final approved = <String>[];
      await pumpConfirm(
        tester,
        deps(
          approveReview:
              (
                _,
                questionId, {
                required expectedVersion,
                expectedAiGradeId,
                note,
              }) async {
                approved.add(questionId);
                return actionResponse(questionId);
              },
        ),
      );

      await scrollThroughMaterial(tester);
      expect(confirmEnabled(tester), isTrue);

      await tester.tap(find.byKey(const Key('confirm-submission-button')));
      await tester.pumpAndSettle();

      // **1回のタップで5設問。** 200回 -> 40回はここで起きている。
      expect(approved, ['q-1', 'q-2', 'q-3', 'q-4', 'q-5']);
    });

    testWidgets('確定する設問の数がボタンに出る', (tester) async {
      await pumpConfirm(
        tester,
        deps(numbers: const ['1', '2', '3'], alreadyConfirmed: const {'q-1'}),
      );
      await scrollThroughMaterial(tester);

      expect(find.text('2問をまとめて確定 (Enter)'), findsOneWidget);
    });

    testWidgets('キーボードだけで確定できる', (tester) async {
      final approved = <String>[];
      await pumpConfirm(
        tester,
        deps(
          numbers: const ['1', '2'],
          approveReview:
              (
                _,
                questionId, {
                required expectedVersion,
                expectedAiGradeId,
                note,
              }) async {
                approved.add(questionId);
                return actionResponse(questionId);
              },
        ),
      );

      // Enter は、未到達が残っている間は「未到達へ送る」である。押しても何も
      // 起きないキーは説明にならない (Issue #85 が Enter に同じ二役を持たせて
      // いるのと同じ)。
      for (var i = 0; i < 40 && !confirmEnabled(tester); i++) {
        await tester.sendKeyEvent(LogicalKeyboardKey.enter);
        await tester.pumpAndSettle();
      }
      expect(confirmEnabled(tester), isTrue);
      expect(approved, isEmpty);

      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();

      expect(approved, ['q-1', 'q-2']);
    });

    testWidgets('別のボタンにフォーカスした Enter は、そのボタンのものである', (tester) async {
      // Enter はページ全体で「確定」に束ねてある。キー入力はフォーカスの位置から
      // 上へ伝わるので、束ね直さないと**後回しにしようとした人が答案を確定する**。
      final approved = <String>[];
      await pumpConfirm(
        tester,
        deps(
          numbers: const ['1'],
          approveReview:
              (
                _,
                questionId, {
                required expectedVersion,
                expectedAiGradeId,
                note,
              }) async {
                approved.add(questionId);
                return actionResponse(questionId);
              },
        ),
      );
      await scrollThroughMaterial(tester);
      expect(confirmEnabled(tester), isTrue);

      // Tab で送る -- キーボードだけの人が実際にそうするのと同じ道である。
      final defer = find.byKey(const Key('confirm-defer-button'));
      var focused = false;
      for (var i = 0; i < 60 && !focused; i++) {
        await tester.sendKeyEvent(LogicalKeyboardKey.tab);
        await tester.pumpAndSettle();
        focused = _isWithin(tester, FocusManager.instance.primaryFocus, defer);
      }
      expect(focused, isTrue, reason: 'Tab で後回しボタンへ到達できていない');

      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pumpAndSettle();

      expect(approved, isEmpty);
      // 後回しの行き先が無いので、そう言うだけで終わる。確定はしていない。
      expect(find.text('ほかに確認できる答案がありません'), findsOneWidget);
    });
  });

  group('部分失敗を隠さない', () {
    testWidgets('3問目で失敗したら、どこまで確定したかを出し、残りを確定し直せる', (tester) async {
      final confirmed = <String>{};
      var failOnThird = true;
      final approved = <String>[];
      final dependencies = AppDependencies(
        getSubmission: (_) async => submission(),
        listQuestions: (_) async => ['1', '2', '3', '4'].map(question).toList(),
        listJobs: (_) async => [
          for (final n in ['1', '2', '3', '4']) job('q-$n'),
        ],
        listRecognitions: (_, questionId) async => [recognition(questionId)],
        listGrades: (_, questionId) async => [grade(questionId)],
        listReviews: (_, questionId) async => confirmed.contains(questionId)
            ? [approvedReview(questionId)]
            : const <ReviewResponse>[],
        getAnswerImage: (_, _) async => throw SidecarApiException(
          SidecarErrorKind.badResponse,
          'not found',
          statusCode: 404,
        ),
        listSubmissions: (_) async => <SubmissionResponse>[submission()],
        listReviewProgress: (_) async =>
            const <SubmissionReviewProgressResponse>[],
        approveReview:
            (
              _,
              questionId, {
              required expectedVersion,
              expectedAiGradeId,
              note,
            }) async {
              approved.add(questionId);
              if (questionId == 'q-3' && failOnThird) {
                throw SidecarApiException(
                  SidecarErrorKind.conflict,
                  '他の操作と競合しました',
                );
              }
              confirmed.add(questionId);
              return actionResponse(questionId);
            },
      );

      await pumpConfirm(tester, dependencies);
      await scrollThroughMaterial(tester);
      await tester.tap(find.byKey(const Key('confirm-submission-button')));
      await tester.pumpAndSettle();

      // **最初の失敗で止める。** 押し通しても失敗が並ぶだけである。
      expect(approved, ['q-1', 'q-2', 'q-3']);

      final notice = tester.widget<Text>(
        find.descendant(
          of: find.byKey(const Key('confirm-outcome-partial')),
          matching: find.byType(Text),
        ),
      );
      // どこまで確定したかが先。「失敗しました」だけでは2問確定した事実が隠れる。
      expect(notice.data, contains('問1・問2 を確定しました'));
      expect(notice.data, contains('問3 で失敗しました'));
      expect(notice.data, contains('他の操作と競合しました'));
      expect(notice.data, contains('残り2問'));

      // 残りだけを確定し直せる。読み直しているので `expectedVersion` も新しい。
      expect(find.text('2問をまとめて確定 (Enter)'), findsOneWidget);

      failOnThird = false;
      approved.clear();
      await tester.tap(find.byKey(const Key('confirm-submission-button')));
      await tester.pumpAndSettle();

      expect(approved, ['q-3', 'q-4']);
      expect(confirmed, {'q-1', 'q-2', 'q-3', 'q-4'});
    });

    testWidgets('1問も確定できなかったときも、そう言う', (tester) async {
      await pumpConfirm(
        tester,
        deps(
          numbers: const ['1', '2'],
          approveReview:
              (
                _,
                questionId, {
                required expectedVersion,
                expectedAiGradeId,
                note,
              }) async => throw SidecarApiException(
                SidecarErrorKind.unavailable,
                'サイドカーに接続できません',
              ),
        ),
      );
      await scrollThroughMaterial(tester);
      await tester.tap(find.byKey(const Key('confirm-submission-button')));
      await tester.pumpAndSettle();

      final notice = tester.widget<Text>(
        find.descendant(
          of: find.byKey(const Key('confirm-outcome-partial')),
          matching: find.byType(Text),
        ),
      );
      expect(notice.data, contains('確定できた設問はありません'));
      expect(notice.data, contains('残り2問'));
    });
  });

  group('確定できない、ほかの理由', () {
    testWidgets('AIが採点できなかった設問があると確定できず、その設問が名指しで出る', (tester) async {
      await pumpConfirm(
        tester,
        deps(numbers: const ['1', '2'], withoutAiGrade: const {'q-2'}),
      );
      await scrollThroughMaterial(tester);

      expect(confirmEnabled(tester), isFalse);
      final notice = tester.widget<Text>(
        find.descendant(
          of: find.byKey(const Key('confirm-blocked-human-score')),
          matching: find.byType(Text),
        ),
      );
      expect(notice.data, contains('問2'));
      // 直せる経路がその場にある。
      expect(find.text('点数を入力する'), findsOneWidget);
    });

    testWidgets('判断材料が読み込めない設問があれば、確定を止めて名指しする', (tester) async {
      final dependencies = AppDependencies(
        getSubmission: (_) async => submission(),
        listQuestions: (_) async => ['1', '2'].map(question).toList(),
        listJobs: (_) async => [job('q-1'), job('q-2')],
        listRecognitions: (_, questionId) async => questionId == 'q-2'
            ? throw SidecarApiException(
                SidecarErrorKind.unavailable,
                'サイドカーに接続できません',
              )
            : [recognition(questionId)],
        listGrades: (_, questionId) async => [grade(questionId)],
        listReviews: (_, _) async => const <ReviewResponse>[],
        getAnswerImage: (_, _) async => throw SidecarApiException(
          SidecarErrorKind.badResponse,
          'not found',
          statusCode: 404,
        ),
        listSubmissions: (_) async => <SubmissionResponse>[submission()],
        listReviewProgress: (_) async =>
            const <SubmissionReviewProgressResponse>[],
      );

      await pumpConfirm(tester, dependencies);

      expect(confirmEnabled(tester), isFalse);
      final notice = tester.widget<Text>(
        find.descendant(
          of: find.byKey(const Key('confirm-blocked-unavailable')),
          matching: find.byType(Text),
        ),
      );
      expect(notice.data, contains('問2'));
    });

    testWidgets('全設問が確定済みの答案は、そう言う', (tester) async {
      await pumpConfirm(
        tester,
        deps(numbers: const ['1', '2'], alreadyConfirmed: const {'q-1', 'q-2'}),
      );

      expect(confirmEnabled(tester), isFalse);
      expect(find.byKey(const Key('confirm-blocked-nothing')), findsOneWidget);
    });

    testWidgets('設問が1つも無ければ、確定ではなくその事実を出す', (tester) async {
      await pumpConfirm(
        tester,
        deps(listQuestions: (_) async => const <QuestionResponse>[]),
      );

      expect(find.byKey(const Key('confirm-no-questions')), findsOneWidget);
    });

    testWidgets('答案そのものが引けなければ、理由と再読み込みを出す', (tester) async {
      await pumpConfirm(
        tester,
        AppDependencies(
          getSubmission: (_) async => throw SidecarApiException(
            SidecarErrorKind.unavailable,
            'サイドカーに接続できません',
          ),
        ),
      );

      expect(find.byKey(const Key('confirm-error')), findsOneWidget);
    });
  });

  group('読み直し', () {
    testWidgets('再読み込みで判断材料を引き直し、到達の記録も測り直す', (tester) async {
      // ポーリングしない画面なので、AI採点がまだ動いている答案には自分で
      // 読み直す手段が要る。**そのとき到達の記録を持ち越さない** -- 中身が
      // 変わったあとの古い記録は、別のものについて「見た」と言っている。
      var loads = 0;
      final dependencies = deps(numbers: const ['1', '2']);
      await pumpConfirm(
        tester,
        AppDependencies(
          getSubmission: dependencies.getSubmission,
          listQuestions: (testId) async {
            loads++;
            return ['1', '2'].map(question).toList();
          },
          listJobs: dependencies.listJobs,
          listRecognitions: dependencies.listRecognitions,
          listGrades: dependencies.listGrades,
          listReviews: dependencies.listReviews,
          getAnswerImage: dependencies.getAnswerImage,
          listSubmissions: dependencies.listSubmissions,
          listReviewProgress: dependencies.listReviewProgress,
          approveReview: dependencies.approveReview,
        ),
      );
      await scrollThroughMaterial(tester);
      expect(confirmEnabled(tester), isTrue);
      expect(loads, 1);

      await tester.tap(find.byKey(const Key('confirm-refresh-button')));
      await tester.pumpAndSettle();

      expect(loads, 2);
      // 一番下まで送った状態から読み直すので、先頭の設問は画面外に戻っている。
      expect(confirmEnabled(tester), isFalse);
    });
  });

  group('直す経路', () {
    testWidgets('設問から添削レビュー画面へ、その設問を開いた状態で入る', (tester) async {
      await pumpConfirm(tester, deps(numbers: const ['1', '2']));

      await tester.scrollUntilVisible(
        find.byKey(const Key('confirm-open-q-2')),
        300,
        scrollable: find.byType(Scrollable).first,
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('confirm-open-q-2')));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      // 添削レビュー画面はサイドカーを引くので描き切らない。確かめたいのは
      // **その答案の**レビューが開いたことなので、ルータが付ける key を見る。
      expect(
        find.byKey(const ValueKey('pdf-review/$testId/$submissionId')),
        findsOneWidget,
      );
    });
  });

  group('見た目', () {
    for (final brightness in Brightness.values) {
      testWidgets('${brightness.name} テーマで描ける', (tester) async {
        await pumpConfirm(
          tester,
          deps(numbers: const ['1', '2']),
          brightness: brightness,
        );

        expect(tester.takeException(), isNull);
        expect(find.byKey(const Key('confirm-question-list')), findsOneWidget);
      });
    }

    testWidgets('キューが引けなければ、何枚目かを書かない', (tester) async {
      // 「1 / 1」と出すと残り1枚だと読まれる。分からないことを、分かっている
      // ように見せない (Issue #113)。
      await pumpConfirm(
        tester,
        deps(
          numbers: const ['1', '2'],
          alreadyConfirmed: const {'q-1'},
        ).copyWithListSubmissionsFailure(),
      );

      // 設問粒度の進捗のほうは、キューと無関係に出せるので消えない。
      final subtitle = tester.widget<Text>(
        find.byKey(const Key('confirm-subtitle')),
      );
      expect(subtitle.data, '確定済み 1 / 2 問');
    });

    testWidgets('キューが引けていれば、何枚目かを出す', (tester) async {
      await pumpConfirm(
        tester,
        deps(
          numbers: const ['1'],
          queueSubmissions: [
            submission(),
            SubmissionResponse(
              (b) => b
                ..id = 'sub-2'
                ..testId = testId
                ..state = 'ai_processed'
                ..pageCount = 1
                ..createdAt = DateTime.utc(2026, 1, 2),
            ),
          ],
        ),
      );

      expect(find.text('1 / 2 件目 ・ 確定済み 0 / 1 問'), findsOneWidget);
    });
  });
}

/// [node] のフォーカスが [ancestor] の中にあるか。
bool _isWithin(WidgetTester tester, FocusNode? node, Finder ancestor) {
  final context = node?.context;
  if (context == null) return false;
  final target = tester.element(ancestor);
  var found = false;
  context.visitAncestorElements((element) {
    if (element != target) return true;
    found = true;
    return false;
  });
  return found;
}

extension on AppDependencies {
  /// 答案キューだけが引けないサイドカー。
  AppDependencies copyWithListSubmissionsFailure() => AppDependencies(
    getSubmission: getSubmission,
    listQuestions: listQuestions,
    listJobs: listJobs,
    listRecognitions: listRecognitions,
    listGrades: listGrades,
    listReviews: listReviews,
    getAnswerImage: getAnswerImage,
    listSubmissions: (_) async =>
        throw SidecarApiException(SidecarErrorKind.unavailable, 'unavailable'),
    approveReview: approveReview,
  );
}
