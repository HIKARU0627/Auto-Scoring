import 'dart:typed_data';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pdfrx/pdfrx.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';

import 'app_harness.dart';
import 'pdfium_bootstrap.dart';

/// **答案1枚を確定し終えるまでの操作数を数える** (Issue #145 受入)。
///
/// 実時間ではなく操作数を測る。実時間は機械と負荷で変わって再現できないが、
/// 操作数はテストが同じ数を何度でも出す。#113 の PR が「200回が残っている」と
/// 書けたのも、体感ではなく数だったからである。
///
/// 数えるのは2つ。
///
/// - **決定の操作** -- 承認・確定のクリック（キーボードなら Enter）。1回押すと
///   サイドカーに確定が飛ぶもの。
/// - **画面遷移** -- 答案キューの行から、その答案を確定し終えるまでに開く画面。
///
/// 送り操作（スクロール）は別に数える。**判断材料を読む量はどちらの経路でも
/// 同じ**で、違うのは「読み進める操作」が承認ボタンを兼ねているか、指の送りに
/// なっているかである。ここを混ぜると、決定の回数が減ったことが見えなくなる。
void main() {
  setUpAll(initializePdfiumForTests);

  const testId = 'test-1';
  const submissionId = 'sub-1';
  const questionNumbers = ['1', '2', '3', '4', '5'];

  /// PoC 3 (Issue #12) の A4 縦 fixture。本物の PDF を本物の pdfium で描く。
  Uint8List pdfBytes() =>
      File('test/fixtures/a4-portrait.pdf').readAsBytesSync();

  SubmissionResponse submission() => SubmissionResponse(
    (b) => b
      ..id = submissionId
      ..testId = testId
      ..state = 'ai_processed'
      ..pageCount = 1
      ..studentLabel = '答案A'
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

  JobResponse job(String questionId) => JobResponse(
    (b) => b
      ..id = 'job-$questionId'
      ..kind = 'grading'
      ..submissionId = submissionId
      ..questionId = questionId
      ..state = 'succeeded'
      ..usable = true
      ..dependencyGraphVersion = 1
      ..attempts = 1
      ..maxAttempts = 3
      ..createdAt = DateTime.utc(2026, 1, 1)
      ..updatedAt = DateTime.utc(2026, 1, 1),
  );

  /// 同じ答案・同じ設問・同じAI結果を、どちらの経路にも同じだけ与える。
  /// 確定した設問は履歴に残るので、2回目以降の読み出しに反映される。
  AppDependencies deps(
    Set<String> confirmed,
    List<String> approved,
  ) => AppDependencies(
    getSubmission: (_) async => submission(),
    getTest: (_) async =>
        throw SidecarApiException(SidecarErrorKind.unavailable, 'not needed'),
    listQuestions: (_) async => questionNumbers.map(question).toList(),
    getSourcePdf: (_) async => pdfBytes(),
    getDependencyGraph: (_) async => throw SidecarApiException(
      SidecarErrorKind.unknown,
      'まだ分析されていません',
      statusCode: 404,
    ),
    listJobs: (_) async => [for (final n in questionNumbers) job('q-$n')],
    listRecognitions: (_, questionId) async => [recognition(questionId)],
    listGrades: (_, questionId) async => [grade(questionId)],
    listAnnotations: (_, _) async => const <AnnotationResponse>[],
    listReviews: (_, questionId) async => confirmed.contains(questionId)
        ? [approvedReview(questionId)]
        : const <ReviewResponse>[],
    getAnswerImage: (_, _) async => throw SidecarApiException(
      SidecarErrorKind.badResponse,
      'not found',
      statusCode: 404,
    ),
    listSubmissions: (_) async => <SubmissionResponse>[submission()],
    listReviewProgress: (_) async => const <SubmissionReviewProgressResponse>[],
    approveReview:
        (
          _,
          questionId, {
          required expectedVersion,
          expectedAiGradeId,
          note,
        }) async {
          approved.add(questionId);
          confirmed.add(questionId);
          return ReviewActionResponse(
            (b) => b
              ..review = approvedReview(questionId).toBuilder()
              ..annotations.replace(const <AnnotationResponse>[])
              ..submissionState = 'ai_processed',
          );
        },
  );

  /// pdfrx (本物の pdfium) の読み込みが落ち着くまで進める。
  Future<void> settlePdf(WidgetTester tester) async {
    await tester.runAsync(() async {
      var ready = 0;
      for (var i = 0; i < 25; i++) {
        await Future<void>.delayed(const Duration(milliseconds: 100));
        await tester.pump(const Duration(milliseconds: 100));
        final viewers = find.byType(PdfViewer).evaluate();
        if (viewers.isEmpty) continue;
        final controller = (viewers.first.widget as PdfViewer).controller;
        if (controller != null && controller.isReady && ++ready == 3) return;
      }
    });
  }

  /// 1回の操作の内訳。
  ///
  /// [decisions] だけが確定をサイドカーへ飛ばす。[transitions] は開いた画面の数、
  /// [scrolls] は判断材料を送った回数。**この3つを混ぜない**のが要点で、
  /// 混ぜると「決定の回数が減った」ことが送り操作に埋もれる。
  ({int decisions, int transitions, int scrolls}) tally({
    required int decisions,
    required int transitions,
    required int scrolls,
  }) => (decisions: decisions, transitions: transitions, scrolls: scrolls);

  testWidgets('答案1枚(5設問)を確定し終えるまでの操作数', (tester) async {
    await tester.binding.setSurfaceSize(const Size(1280, 720));
    addTearDown(() => tester.binding.setSurfaceSize(null));

    // ------------------------------------------------ 変更前: 設問ごとの承認
    //
    // 添削レビュー画面は設問1件の画面である。承認すると次の設問へ進むので、
    // 「読み進める」と「確定する」が同じボタンに乗っている。
    final beforeApproved = <String>[];
    var beforeDecisions = 0;
    var beforeScrolls = 0;
    await pumpAppAt(
      tester,
      AppRoutes.pdfReview(testId: testId, submissionId: submissionId),
      dependencies: deps(<String>{}, beforeApproved),
    );
    // 答案キューの行を1回タップして開いた、という1遷移。
    const beforeTransitions = 1;
    await settlePdf(tester);
    for (var i = 0; i < 5; i++) {
      // 判断材料が画面外に残っていれば、まず表示する (Issue #85 のゲート)。
      for (var page = 0; page < 40; page++) {
        final reveal = find.byKey(const Key('review-reveal-material-button'));
        if (reveal.evaluate().isEmpty) break;
        await tester.tap(reveal);
        await tester.pumpAndSettle();
        beforeScrolls++;
      }
      await tester.tap(find.byKey(const Key('review-approve-button')));
      await tester.pumpAndSettle();
      beforeDecisions++;
    }
    final before = tally(
      decisions: beforeDecisions,
      transitions: beforeTransitions,
      scrolls: beforeScrolls,
    );
    expect(beforeApproved.toSet(), {'q-1', 'q-2', 'q-3', 'q-4', 'q-5'});

    // ------------------------------------------------ 変更後: 答案ごとの確定
    //
    // 前の画面を先に畳む。同じテストの中で2つ目のアプリを立てると、1つ目の
    // ルータが積んだページが Overlay に残ったまま重なり、次の画面のボタンに
    // 触れなくなる。
    await tester.pumpWidget(const SizedBox.shrink());
    await tester.pumpAndSettle();

    final afterApproved = <String>[];
    var afterScrolls = 0;
    await pumpAppAt(
      tester,
      AppRoutes.submissionConfirm(testId: testId, submissionId: submissionId),
      dependencies: deps(<String>{}, afterApproved),
    );
    await tester.pumpAndSettle();
    const afterTransitions = 1;
    final list = find.byKey(const Key('confirm-question-list'));
    for (var drags = 0; drags < 40; drags++) {
      final button = tester.widget<FilledButton>(
        find.byKey(const Key('confirm-submission-button')),
      );
      if (button.onPressed != null) break;
      await tester.drag(list, const Offset(0, -300));
      await tester.pumpAndSettle();
      afterScrolls++;
    }
    await tester.tap(find.byKey(const Key('confirm-submission-button')));
    await tester.pumpAndSettle();
    final after = tally(
      decisions: 1,
      transitions: afterTransitions,
      scrolls: afterScrolls,
    );
    expect(afterApproved, ['q-1', 'q-2', 'q-3', 'q-4', 'q-5']);

    // ------------------------------------------------------------------ 結果
    //
    // **決定の操作が 5 -> 1 になる。** 40枚なら 200 -> 40 である。画面遷移は
    // 変わらない (どちらも答案キューの行を1回タップして入る)。
    expect(before.decisions, 5);
    expect(after.decisions, 1);
    expect(before.transitions, after.transitions);

    // 送り操作は増える。**増えることを隠さない** -- 判断材料を読む量は同じで、
    // 変更前はその送りを承認ボタンが兼ねていた。決定の回数が減ったぶん、送りが
    // 指の側に出てきている。
    expect(after.scrolls, greaterThan(before.scrolls));

    // PR に貼るのはこの行である。
    // ignore: avoid_print
    print(
      '[Issue #145] 1答案(5設問)あたりの操作数 '
      '決定: ${before.decisions} -> ${after.decisions} / '
      '画面遷移: ${before.transitions} -> ${after.transitions} / '
      '送り: ${before.scrolls} -> ${after.scrolls}',
    );
  });
}
