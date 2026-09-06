import 'dart:async';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pdfrx/pdfrx.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/features/pdf_review/pdf_review_page.dart';

/// The PoC 3 (Issue #12) A4-portrait fixture: a real, tiny single-page PDF
/// with the same 5 normalized test points stamped on it as red marks
/// (`docs/poc-3-pdf-coordinates.md`). Reused here so the overlay-position
/// test below renders against a real PDF through the real `pdfrx`/pdfium
/// pipeline, not a hand-rolled stand-in.
Uint8List _pocA4PortraitPdf() =>
    File('test/fixtures/a4-portrait.pdf').readAsBytesSync();

SubmissionResponse _submission({
  String id = 'sub-1',
  String state = 'needs_review',
  String? studentLabel = 'student-a',
}) => SubmissionResponse(
  (b) => b
    ..id = id
    ..testId = 'test-1'
    ..state = state
    ..pageCount = 1
    ..studentLabel = studentLabel
    ..createdAt = DateTime.utc(2026, 1, 1),
);

QuestionResponse _question({
  String id = 'q-1',
  String number = '1',
  int page = 1,
  List<RubricCriterionResponse> rubric = const [],
  NormalizedRectResponse? rect,
}) => QuestionResponse(
  (b) => b
    ..id = id
    ..testId = 'test-1'
    ..number = number
    ..page = page
    ..points = 5
    ..scoringMethod = 'additive'
    ..rubric.replace(rubric)
    ..commentArea = rect?.toBuilder(),
);

RecognitionResponse _recognition({
  String id = 'rec-1',
  String questionId = 'q-1',
  String text = '光合成によって酸素が発生する',
  double confidence = 0.91,
}) => RecognitionResponse(
  (b) => b
    ..id = id
    ..submissionId = 'sub-1'
    ..questionId = questionId
    ..source_ = 'ai'
    ..text = text
    ..confidence = confidence
    ..createdAt = DateTime.utc(2026, 1, 1),
);

GradeResultResponse _grade({
  String id = 'grade-1',
  String questionId = 'q-1',
  int awarded = 4,
  int maximum = 5,
  double confidence = 0.88,
  String? rationale = '理由の説明が不足しています。',
  List<CriterionResultResponse> criteria = const [],
}) => GradeResultResponse(
  (b) => b
    ..id = id
    ..submissionId = 'sub-1'
    ..questionId = questionId
    ..source_ = 'ai'
    ..score.awarded = awarded
    ..score.maximum = maximum
    ..score.ratio = awarded / maximum
    ..confidence = confidence
    ..rationale = rationale
    ..criteria.replace(criteria)
    ..createdAt = DateTime.utc(2026, 1, 1),
);

AnnotationResponse _annotation({
  String id = 'anno-1',
  String questionId = 'q-1',
  String kind = 'circle',
  NormalizedRectResponse? rect,
  String? comment,
}) => AnnotationResponse(
  (b) => b
    ..id = id
    ..submissionId = 'sub-1'
    ..questionId = questionId
    ..source_ = 'ai'
    ..kind = kind
    ..rect = rect?.toBuilder()
    ..comment = comment
    ..createdAt = DateTime.utc(2026, 1, 1),
);

NormalizedRectResponse _rect(double x, double y, double w, double h) =>
    NormalizedRectResponse(
      (b) => b
        ..x = x
        ..y = y
        ..width = w
        ..height = h,
    );

/// Builds an [AppDependencies] pre-wired for a single question ([q1]) with
/// [recognitions]/[grades]/[annotations] and (optionally) a second question
/// ([q2]), all served from a real [pdfBytes] PDF.
AppDependencies _dependencies({
  required Uint8List pdfBytes,
  required QuestionResponse q1,
  QuestionResponse? q2,
  List<RecognitionResponse> recognitions = const [],
  List<GradeResultResponse> grades = const [],
  List<AnnotationResponse> annotations = const [],
  SubmissionResponse? submission,
}) {
  final questions = [q1, ?q2];
  return AppDependencies(
    getSubmission: (submissionId) async => submission ?? _submission(),
    listQuestions: (testId) async => questions,
    getSourcePdf: (submissionId) async => pdfBytes,
    listRecognitions: (submissionId, questionId) async =>
        recognitions.where((r) => r.questionId == questionId).toList(),
    listGrades: (submissionId, questionId) async =>
        grades.where((g) => g.questionId == questionId).toList(),
    listAnnotations: (submissionId, questionId) async =>
        annotations.where((a) => a.questionId == questionId).toList(),
  );
}

Widget _wrap(Widget child) => MaterialApp(home: child);

/// Pumps until pdfrx's real (native pdfium) document load settles.
/// `tester.pump()` alone only advances the fake test clock, not the real
/// wall-clock async work pdfium's FFI calls run on -- see
/// `Pdfrx.cacheDirectoryPath` below for why the platform-channel half of
/// that startup path needs sidestepping under `flutter test` too.
Future<void> _settlePdf(WidgetTester tester) async {
  await tester.runAsync(() async {
    for (var i = 0; i < 25; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 100));
    }
  });
}

void main() {
  setUpAll(() {
    // pdfrxFlutterInitialize() otherwise calls path_provider's
    // getTemporaryDirectory() over a platform channel that `flutter test`
    // has no implementation for (MissingPluginException). Pre-setting this
    // skips that call entirely; it never actually needs a *writable* cache
    // for these fixture sizes.
    Pdfrx.cacheDirectoryPath = Directory.systemTemp.path;
  });

  testWidgets('shows a loading indicator before the shell finishes loading', (
    tester,
  ) async {
    final dependencies = AppDependencies(
      getSubmission: (_) => Completer<SubmissionResponse>().future,
      listQuestions: (_) => Completer<List<QuestionResponse>>().future,
      getSourcePdf: (_) => Completer<Uint8List>().future,
    );

    await tester.pumpWidget(
      _wrap(
        PdfReviewPage(
          dependencies: dependencies,
          testId: 'test-1',
          submissionId: 'sub-1',
        ),
      ),
    );

    expect(find.byKey(const Key('review-loading')), findsOneWidget);
  });

  testWidgets('shows an error banner with a working retry action', (
    tester,
  ) async {
    var attempts = 0;
    final dependencies = AppDependencies(
      getSubmission: (_) async {
        attempts++;
        if (attempts == 1) {
          throw SidecarApiException(SidecarErrorKind.unavailable, 'offline');
        }
        return _submission();
      },
      listQuestions: (_) async => [_question()],
      getSourcePdf: (_) async => _pocA4PortraitPdf(),
    );

    await tester.pumpWidget(
      _wrap(
        PdfReviewPage(
          dependencies: dependencies,
          testId: 'test-1',
          submissionId: 'sub-1',
        ),
      ),
    );
    await tester.pump();

    expect(find.byKey(const Key('review-shell-error')), findsOneWidget);
    expect(find.text('offline'), findsOneWidget);

    await tester.tap(find.text('再試行'));
    await tester.pump();
    await _settlePdf(tester);

    expect(find.byKey(const Key('review-shell-error')), findsNothing);
  });

  testWidgets('shows an empty state when the test has no questions', (
    tester,
  ) async {
    final dependencies = AppDependencies(
      getSubmission: (_) async => _submission(),
      listQuestions: (_) async => const [],
      getSourcePdf: (_) async => _pocA4PortraitPdf(),
    );

    await tester.pumpWidget(
      _wrap(
        PdfReviewPage(
          dependencies: dependencies,
          testId: 'test-1',
          submissionId: 'sub-1',
        ),
      ),
    );
    await tester.pump();

    expect(find.byKey(const Key('review-empty-shell')), findsOneWidget);
  });

  testWidgets(
    'shows recognition, score, rationale, rubric, and dual confidence for '
    'the same question, distinguished by text/icon not just color',
    (tester) async {
      // find.bySemanticsLabel below needs the semantics tree actually built
      // -- flutter_test does not build it by default. Disposed explicitly
      // at the end of this test body (not via addTearDown): the
      // framework's "every SemanticsHandle was disposed" check runs at the
      // tail of the test body itself, before any addTearDown callback would
      // get a chance to run.
      final semantics = tester.ensureSemantics();
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(
          rubric: const [], // rubric criteria come from the grade below
        ),
        recognitions: [_recognition(confidence: 0.55)],
        grades: [
          _grade(
            confidence: 0.97,
            criteria: [
              CriterionResultResponse(
                (b) => b
                  ..criterionId = 'c-1'
                  ..outcome = 'pass'
                  ..confidence = 0.9,
              ),
            ],
          ),
        ],
        submission: _submission(state: 'needs_review'),
      );

      await tester.pumpWidget(
        _wrap(
          PdfReviewPage(
            dependencies: dependencies,
            testId: 'test-1',
            submissionId: 'sub-1',
          ),
        ),
      );
      await tester.pump();
      await _settlePdf(tester);

      expect(
        find.text('光合成によって酸素が発生する'),
        findsOneWidget,
        reason: 'AI recognized text is shown',
      );
      expect(find.text('4 / 5 点'), findsOneWidget, reason: 'score is shown');
      expect(
        find.text('理由の説明が不足しています。'),
        findsOneWidget,
        reason: 'grading rationale is shown',
      );
      expect(
        find.text('c-1'),
        findsOneWidget,
        reason: 'rubric criterion is shown',
      );

      // Both confidences are visible side by side, distinguished by their
      // numeric value + a Japanese level label -- never by color alone.
      expect(find.text('文字認識信頼度: 55% (低)'), findsOneWidget);
      expect(find.text('採点信頼度: 97% (高)'), findsOneWidget);

      // Screen reader labels exist for both confidence badges, independent
      // of the visible text rendering above.
      expect(find.bySemanticsLabel('文字認識信頼度 55% 低'), findsOneWidget);
      expect(find.bySemanticsLabel('採点信頼度 97% 高'), findsOneWidget);

      // The submission's processing state is identifiable via icon + text.
      expect(find.byKey(const Key('review-submission-state')), findsOneWidget);
      expect(find.text('要確認'), findsOneWidget);

      semantics.dispose();
    },
  );

  testWidgets('routes an annotation with no target Bounding Box to the comment '
      'fallback area instead of dropping it', (tester) async {
    final dependencies = _dependencies(
      pdfBytes: _pocA4PortraitPdf(),
      q1: _question(),
      annotations: [
        _annotation(kind: 'comment', rect: null, comment: '時制表現について確認'),
      ],
    );

    await tester.pumpWidget(
      _wrap(
        PdfReviewPage(
          dependencies: dependencies,
          testId: 'test-1',
          submissionId: 'sub-1',
        ),
      ),
    );
    await tester.pump();
    await _settlePdf(tester);

    expect(find.text('設問コメント'), findsOneWidget);
    expect(find.text('時制表現について確認'), findsOneWidget);
  });

  testWidgets('places a target-anchored annotation on the PDF overlay at its '
      "normalized position, using the page's real rendered size", (
    tester,
  ) async {
    final mark = _rect(0.5, 0.5, 0.05, 0.05); // a PoC 3 test point
    final dependencies = _dependencies(
      pdfBytes: _pocA4PortraitPdf(),
      q1: _question(),
      annotations: [_annotation(kind: 'circle', rect: mark)],
    );

    await tester.pumpWidget(
      _wrap(
        PdfReviewPage(
          dependencies: dependencies,
          testId: 'test-1',
          submissionId: 'sub-1',
        ),
      ),
    );
    await tester.pump();
    await _settlePdf(tester);

    final overlay = find.byKey(const Key('annotation-anno-1'));
    expect(overlay, findsOneWidget);

    // pdfrx fits the page to the viewer's available space, so its actual
    // on-screen size depends on the test surface -- read the real page
    // rect pdfrx computed (the `Positioned` it wraps every page's overlay
    // `Stack` in, see `pdf_viewer.dart`'s `_buildPageOverlayWidgets`)
    // instead of assuming A4's 595x842pt natural size renders 1:1.
    final pageOverlayPositioned = tester.widget<Positioned>(
      find.byKey(const Key('#__pageOverlay__:1')),
    );
    final pageRect = Rect.fromLTWH(
      pageOverlayPositioned.left!,
      pageOverlayPositioned.top!,
      pageOverlayPositioned.width!,
      pageOverlayPositioned.height!,
    );

    final overlayTopLeft = tester.getTopLeft(overlay);
    final pdfViewerTopLeft = tester.getTopLeft(find.byType(PdfViewer));
    final localOffset = overlayTopLeft - pdfViewerTopLeft;

    // The same normalized point (0.5, 0.5) PoC 3 (Issue #12) verified
    // round-trips through pdfium, now placed by the production overlay
    // code against whatever size pdfrx actually rendered the page at.
    expect(localOffset.dx, closeTo(pageRect.left + 0.5 * pageRect.width, 5.0));
    expect(localOffset.dy, closeTo(pageRect.top + 0.5 * pageRect.height, 5.0));
  });

  testWidgets('keeps the same overlay alignment after the page is rotated 90° '
      '(PoC 3 a4-rotate-90 fixture)', (tester) async {
    final mark = _rect(0.5, 0.5, 0.05, 0.05); // the same PoC 3 test point
    final dependencies = _dependencies(
      pdfBytes: File('test/fixtures/a4-rotate-90.pdf').readAsBytesSync(),
      q1: _question(),
      annotations: [_annotation(kind: 'circle', rect: mark)],
    );

    await tester.pumpWidget(
      _wrap(
        PdfReviewPage(
          dependencies: dependencies,
          testId: 'test-1',
          submissionId: 'sub-1',
        ),
      ),
    );
    await tester.pump();
    await _settlePdf(tester);

    final overlay = find.byKey(const Key('annotation-anno-1'));
    expect(overlay, findsOneWidget);

    // Same reasoning as the unrotated case above: read pdfrx's actual
    // reported page rect (already post-/Rotate, per PoC 3's "displayed =
    // (nx·Wd, ny·Hd)" contract) instead of assuming a fixed pixel size.
    final pageOverlayPositioned = tester.widget<Positioned>(
      find.byKey(const Key('#__pageOverlay__:1')),
    );
    final pageRect = Rect.fromLTWH(
      pageOverlayPositioned.left!,
      pageOverlayPositioned.top!,
      pageOverlayPositioned.width!,
      pageOverlayPositioned.height!,
    );

    final overlayTopLeft = tester.getTopLeft(overlay);
    final pdfViewerTopLeft = tester.getTopLeft(find.byType(PdfViewer));
    final localOffset = overlayTopLeft - pdfViewerTopLeft;

    expect(localOffset.dx, closeTo(pageRect.left + 0.5 * pageRect.width, 5.0));
    expect(localOffset.dy, closeTo(pageRect.top + 0.5 * pageRect.height, 5.0));
  });

  testWidgets(
    'keyboard: arrow keys move between questions and Enter approves and '
    'advances, without needing the mouse',
    (tester) async {
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(id: 'q-1', number: '1'),
        q2: _question(id: 'q-2', number: '2'),
        recognitions: [
          _recognition(questionId: 'q-1', text: '設問1の答案'),
          _recognition(questionId: 'q-2', text: '設問2の答案'),
        ],
      );

      await tester.pumpWidget(
        _wrap(
          PdfReviewPage(
            dependencies: dependencies,
            testId: 'test-1',
            submissionId: 'sub-1',
          ),
        ),
      );
      await tester.pump();
      await _settlePdf(tester);

      expect(find.text('設問1の答案'), findsOneWidget);

      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pump();
      await _settlePdf(tester);
      expect(find.text('設問2の答案'), findsOneWidget);

      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pump();
      await _settlePdf(tester);
      expect(find.text('設問1の答案'), findsOneWidget);

      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      await _settlePdf(tester);
      // Approving question 1 while it was showing moves to question 2.
      expect(find.text('設問2の答案'), findsOneWidget);
    },
  );

  testWidgets('the action bar (修正/却下/承認して次へ) is reachable via keyboard focus '
      'traversal, with focus visualized', (tester) async {
    final dependencies = _dependencies(
      pdfBytes: _pocA4PortraitPdf(),
      q1: _question(),
    );

    await tester.pumpWidget(
      _wrap(
        PdfReviewPage(
          dependencies: dependencies,
          testId: 'test-1',
          submissionId: 'sub-1',
        ),
      ),
    );
    await tester.pump();
    await _settlePdf(tester);

    for (final key in [
      'review-edit-button',
      'review-reject-button',
      'review-approve-button',
    ]) {
      final finder = find.byKey(Key(key));
      expect(finder, findsOneWidget);
      final buttonWidget = tester.widget(finder);
      expect(buttonWidget, isA<ButtonStyleButton>());
    }

    // Reachable and focusable without a pointer: Focus.of a button's
    // context can request focus directly, exercising the same focus
    // node keyboard Tab traversal would land on.
    final approveContext = tester.element(
      find.byKey(const Key('review-approve-button')),
    );
    Focus.of(approveContext).requestFocus();
    await tester.pump();
    expect(Focus.of(approveContext).hasPrimaryFocus, isTrue);
  });

  testWidgets('lays out without overflow at a narrow desktop width', (
    tester,
  ) async {
    addTearDown(tester.view.resetPhysicalSize);
    tester.view.physicalSize = const Size(700, 900);
    tester.view.devicePixelRatio = 1.0;

    final dependencies = _dependencies(
      pdfBytes: _pocA4PortraitPdf(),
      q1: _question(),
      recognitions: [_recognition()],
      grades: [_grade()],
    );

    await tester.pumpWidget(
      _wrap(
        PdfReviewPage(
          dependencies: dependencies,
          testId: 'test-1',
          submissionId: 'sub-1',
        ),
      ),
    );
    await tester.pump();
    await _settlePdf(tester);

    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('review-inspector')), findsOneWidget);
  });
}
