import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:pdfrx/pdfrx.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/features/pdf_review/pdf_review_page.dart';
import 'package:auto_scoring_app/features/review_queue/submission_queue_page.dart';

import 'app_harness.dart';

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
  NormalizedRectResponse? answerArea,
}) => QuestionResponse(
  (b) => b
    ..id = id
    ..testId = 'test-1'
    ..number = number
    ..page = page
    ..points = 5
    ..scoringMethod = 'additive'
    ..rubric.replace(rubric)
    ..commentArea = rect?.toBuilder()
    ..answerArea = answerArea?.toBuilder(),
);

RecognitionResponse _recognition({
  String id = 'rec-1',
  String questionId = 'q-1',
  String text = '光合成によって酸素が発生する',
  double confidence = 0.91,
  String stage = 'ocr',
  List<BoundingBoxResponse> boxes = const [],
  DateTime? createdAt,
}) => RecognitionResponse(
  (b) => b
    ..id = id
    ..submissionId = 'sub-1'
    ..questionId = questionId
    ..source_ = 'ai'
    ..stage = stage
    ..text = text
    ..confidence = confidence
    ..boxes.replace(boxes)
    ..createdAt = createdAt ?? DateTime.utc(2026, 1, 1),
);

GradeResultResponse _grade({
  String id = 'grade-1',
  String questionId = 'q-1',
  int awarded = 4,
  int maximum = 5,
  double confidence = 0.88,
  String? rationale = '理由の説明が不足しています。',
  String? comment,
  List<CriterionResultResponse> criteria = const [],
  AnswerImageFinding? answerImageFinding,
  DateTime? createdAt,
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
    ..comment = comment
    ..criteria.replace(criteria)
    ..answerImageFinding = answerImageFinding
    ..createdAt = createdAt ?? DateTime.utc(2026, 1, 1),
);

AnnotationResponse _annotation({
  String id = 'anno-1',
  String questionId = 'q-1',
  String kind = 'circle',
  NormalizedRectResponse? rect,
  String? comment,
  DateTime? createdAt,
}) => AnnotationResponse(
  (b) => b
    ..id = id
    ..submissionId = 'sub-1'
    ..questionId = questionId
    ..source_ = 'ai'
    ..kind = kind
    ..rect = rect?.toBuilder()
    ..comment = comment
    ..createdAt = createdAt ?? DateTime.utc(2026, 1, 1),
);

JobResponse _jobFor(
  String questionId, {
  String state = 'succeeded',
  bool? usable = true,
  String? blockedOnQuestionId,
  int graphVersion = 1,
  String? lastError,
}) => JobResponse(
  (b) => b
    ..id = 'job-$questionId-v$graphVersion'
    ..kind = 'grading'
    ..submissionId = 'sub-1'
    ..questionId = questionId
    ..state = state
    ..usable = usable
    ..blockedOnQuestionId = blockedOnQuestionId
    ..lastError = lastError
    ..dependencyGraphVersion = graphVersion
    ..attempts = 1
    ..maxAttempts = 3
    ..createdAt = DateTime.utc(2026, 1, 1, graphVersion)
    ..updatedAt = DateTime.utc(2026, 1, 1, graphVersion),
);

/// A one-edge graph: by default 問1 must finish before 問2 may start.
DependencyGraphResponse _dependencyGraph({
  String status = 'confirmed',
  int version = 1,
  String from = 'q-1',
  String to = 'q-2',
}) => DependencyGraphResponse(
  (b) => b
    ..id = 'graph-$version'
    ..testId = 'test-1'
    ..version = version
    ..status = status
    ..questionIds.replace(const ['q-1', 'q-2'])
    ..edges.replace([
      DependencyEdgeModel(
        (e) => e
          ..fromQuestionId = from
          ..toQuestionId = to
          ..rationale = '前の設問の結論を使う'
          ..provides.replace(const <DependencyProvision>[]),
      ),
    ])
    ..unresolved.replace(const <UnresolvedQuestionModel>[])
    ..createdAt = DateTime.utc(2026, 1, 1)
    ..confirmedAt = status == 'confirmed' ? DateTime.utc(2026, 1, 1) : null,
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
  List<ReviewResponse> reviews = const [],
  SubmissionResponse? submission,
  DependencyGraphResponse? graph,
  List<JobResponse> jobs = const [],
  EditReview? editReview,
  GradeManually? gradeManually,
  RejectReview? rejectReview,
  RegradeReview? regradeReview,
  ApproveReview? approveReview,
  UndoReview? undoReview,
  List<SubmissionResponse>? queueSubmissions,
  GetTest? getTest,
}) {
  final questions = [
    q1,
    ?q2,
    if (graph != null)
      for (final id in graph.questionIds.where(
        (id) => id != q1.id && id != q2?.id,
      ))
        _question(id: id, number: id.split('-').last),
  ];
  return AppDependencies(
    getSubmission: (submissionId) async => submission ?? _submission(),
    // 「答案キューへ」で移った先の答案キュー画面が引くもの。既定は
    // 「未接続」のまま -- 添削レビュー画面自身はテストを引かない (Issue #160)。
    getTest:
        getTest ??
        (testId) async => throw SidecarApiException(
          SidecarErrorKind.unavailable,
          'sidecar is not connected',
        ),
    // 添削レビュー画面は答案キューを引いて「何枚目か」「次はどれか」を出す
    // (Issue #113)。既定は空 -- キューが引けない画面も成立しなければならない。
    listSubmissions: (testId) async =>
        queueSubmissions ?? const <SubmissionResponse>[],
    listQuestions: (testId) async => questions,
    getSourcePdf: (submissionId) async => pdfBytes,
    getDependencyGraph: (testId) async =>
        graph ??
        (throw SidecarApiException(
          SidecarErrorKind.unknown,
          'まだ分析されていません',
          statusCode: 404,
        )),
    listJobs: (submissionId) async => jobs,
    listRecognitions: (submissionId, questionId) async =>
        recognitions.where((r) => r.questionId == questionId).toList(),
    listGrades: (submissionId, questionId) async =>
        grades.where((g) => g.questionId == questionId).toList(),
    listAnnotations: (submissionId, questionId) async =>
        annotations.where((a) => a.questionId == questionId).toList(),
    listReviews: (submissionId, questionId) async =>
        reviews.where((r) => r.questionId == questionId).toList(),
    // Generic "it succeeded" defaults so a test exercising keyboard/button
    // navigation doesn't need to hand-wire every action -- a test asserting
    // something more specific (the exact request sent, a conflict) passes
    // its own fake instead.
    editReview:
        editReview ??
        (
          submissionId,
          questionId, {
          required expectedVersion,
          expectedAiGradeId,
          required scoreAwarded,
          required scoreMaximum,
          confidence = 1.0,
          criteria = const [],
          rationale,
          comment,
          recognizedText,
          annotations,
          note,
        }) async => _reviewAction(
          _review(
            questionId: questionId,
            action: 'modified',
            version: expectedVersion + 1,
            humanGradeResultId: 'grade-human-$questionId-$expectedVersion',
          ),
        ),
    gradeManually:
        gradeManually ??
        (
          submissionId,
          questionId, {
          required expectedVersion,
          required scoreAwarded,
          required scoreMaximum,
          confidence = 1.0,
          criteria = const [],
          rationale,
          comment,
          recognizedText,
          annotations,
          note,
        }) async => _reviewAction(
          _review(
            questionId: questionId,
            action: 'modified',
            version: expectedVersion + 1,
            aiGradeResultId: null,
            humanGradeResultId: 'grade-manual-$questionId-$expectedVersion',
          ),
        ),
    rejectReview:
        rejectReview ??
        (submissionId, questionId, {required expectedVersion, reason}) async =>
            _reviewAction(
              _review(
                questionId: questionId,
                action: 'rejected',
                version: expectedVersion + 1,
              ),
            ),
    regradeReview:
        regradeReview ??
        (submissionId, questionId, {required expectedVersion, reason}) async =>
            _reviewAction(
              _review(
                questionId: questionId,
                action: 'regrade_requested',
                version: expectedVersion + 1,
                regradeJobId: 'job-regrade-$questionId-$expectedVersion',
              ),
              jobId: 'job-regrade-$questionId-$expectedVersion',
            ),
    approveReview:
        approveReview ??
        (
          submissionId,
          questionId, {
          required expectedVersion,
          expectedAiGradeId,
          note,
        }) async => _reviewAction(
          _review(
            questionId: questionId,
            action: 'approved',
            version: expectedVersion + 1,
          ),
        ),
    undoReview:
        undoReview ??
        (submissionId, questionId, {required expectedVersion}) async =>
            _reviewAction(
              _review(
                questionId: questionId,
                action: 'undone',
                version: expectedVersion + 1,
                undoneReviewId: 'review-undone-$questionId',
              ),
            ),
  );
}

ReviewResponse _review({
  String id = 'review-1',
  String questionId = 'q-1',
  String action = 'approved',
  int version = 1,
  String? aiGradeResultId = 'grade-1',
  String? humanGradeResultId,
  String? regradeJobId,
  String? undoneReviewId,
  String? note,
  DateTime? createdAt,
}) => ReviewResponse(
  (b) => b
    ..id = id
    ..submissionId = 'sub-1'
    ..questionId = questionId
    ..action = action
    ..version = version
    ..aiGradeResultId = aiGradeResultId
    ..humanGradeResultId = humanGradeResultId
    ..regradeJobId = regradeJobId
    ..undoneReviewId = undoneReviewId
    ..note = note
    ..createdAt = createdAt ?? DateTime.utc(2026, 1, 1),
);

/// A [ReviewActionResponse] wrapping [review], for a fake
/// edit/reject/regrade/approve/undo callback to return.
ReviewActionResponse _reviewAction(
  ReviewResponse review, {
  GradeResultResponse? grade,
  RecognitionResponseSlim? recognition,
  List<AnnotationResponse> annotations = const [],
  String? jobId,
  String submissionState = 'needs_review',
}) => ReviewActionResponse(
  (b) => b
    ..review = review.toBuilder()
    ..grade = grade?.toBuilder()
    ..recognition = recognition?.toBuilder()
    ..annotations.replace(annotations)
    ..jobId = jobId
    ..submissionState = submissionState,
);

/// Brings the whole of the current question's 判断材料 on screen, which is
/// what 承認 has been gated on since Issue #85: a test that means to exercise
/// 承認 has to have looked at the material first, exactly as a reviewer does.
/// A no-op when the panel already fits.
Future<void> _revealMaterial(WidgetTester tester) async {
  // Press 「続きを表示」 -- the control the screen itself offers -- rather than
  // driving the scroll position. The button has to take the reviewer to the
  // unread material, and that is not always downwards (Issue #85, レビュー
  // 5回目 P2), so a helper that scrolled down by hand would pass while the
  // offered way out did nothing.
  //
  // Deliberately a no-op unless the gate is actually closed. If it pressed
  // regardless, a regression that made the gate fire on a panel with nothing
  // below the fold would slip through every test that calls this.
  for (var page = 0; page < 60; page++) {
    final reveal = find.byKey(const Key('review-reveal-material-button'));
    if (reveal.evaluate().isEmpty) return;
    await tester.tap(reveal);
    await tester.pumpAndSettle();
  }
}

/// Opens 添削レビュー画面 for `test-1` / `sub-1` with [dependencies] in place
/// of a live sidecar.
Future<void> _pumpReview(WidgetTester tester, AppDependencies dependencies) =>
    pumpAppAt(
      tester,
      AppRoutes.pdfReview(testId: 'test-1', submissionId: 'sub-1'),
      dependencies: dependencies,
    );

/// Pumps until pdfrx's real (native pdfium) document load settles.
/// `tester.pump()` alone only advances the fake test clock, not the real
/// wall-clock async work pdfium's FFI calls run on -- see
/// `Pdfrx.cacheDirectoryPath` below for why the platform-channel half of
/// that startup path needs sidestepping under `flutter test` too.
///
/// Stops as soon as the viewer reports its pages instead of always sleeping
/// out the cap. The load itself finishes in ~220 ms, so waiting the full 25
/// steps every time cost 2.5 s on each of this file's ~120 calls -- five
/// minutes per CI run spent idle, and the single longest pole in `pnpm test`
/// (Issue #129). The 25 steps stay as a *timeout*, so a slower machine keeps
/// exactly the headroom it had before.
Future<void> _settlePdf(WidgetTester tester) async {
  await tester.runAsync(() async {
    var framesSinceReady = 0;
    for (var i = 0; i < 25; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 100));
      await tester.pump(const Duration(milliseconds: 100));
      // `isReady` flips when pdfium has parsed the document, which is a frame
      // earlier than the overlays laid out from those pages reach the tree --
      // so give it two more before handing back.
      if (_pdfPagesAreReady(tester) && ++framesSinceReady == 3) return;
    }
  });
}

/// Advances past the screen's 3-second background poll and lets the fetch it
/// starts land.
///
/// The poll is a `Timer.periodic` created inside the test, so it runs on the
/// *fake* clock and only `tester.pump(duration)` moves it -- the real-time
/// `Future.delayed` these call sites used to wait on never advanced it by a
/// single tick. What actually fired the poll was the old `_settlePdf`, which
/// pumped 2.5 fake seconds on every call as a side effect of its fixed wait.
/// Now that it stops as soon as the PDF is ready, the tests that mean to
/// exercise the poll have to say so (Issue #129).
Future<void> _settlePoll(WidgetTester tester) async {
  await tester.runAsync(() async {
    // 5 fake seconds, comfortably past one 3-second tick, in steps small
    // enough that the fetch each tick starts is awaited rather than raced.
    for (var i = 0; i < 25; i++) {
      await Future<void>.delayed(const Duration(milliseconds: 10));
      await tester.pump(const Duration(milliseconds: 200));
    }
  });
}

/// Whether the screen's [PdfViewer] has finished parsing its document.
///
/// False while no viewer is mounted at all, which is the right answer for the
/// callers whose PDF future never completes: they wait out the full cap, just
/// as every caller used to.
bool _pdfPagesAreReady(WidgetTester tester) {
  final viewers = find.byType(PdfViewer).evaluate();
  if (viewers.isEmpty) return false;
  final controller = (viewers.first.widget as PdfViewer).controller;
  return controller != null && controller.isReady;
}

/// Pumps [times] frames without advancing the clock, to let a chain of
/// already-resolved Futures land. `pumpAndSettle` cannot be used on this
/// screen while any job is still in flight: the 3-second poll keeps
/// scheduling frames, so nothing ever settles.
Future<void> _pumpTimes(WidgetTester tester, int times) async {
  for (var i = 0; i < times; i++) {
    await tester.pump();
  }
}

/// The pdfium shared library that `flutter test` builds but never wires up,
/// or `null` when this platform does not need the detour.
///
/// `pdfium_dart`'s loader finds pdfium either next to a *built* Flutter
/// application (`<executable>/../lib/libpdfium.so`) or through
/// `.dart_tool/native_assets.yaml`, which only `dart test`/`dart run` write.
/// Under `flutter test` on Linux the executable is `flutter_tester` and there
/// is no native-assets file, so every test that renders the real fixture PDF
/// died with "Failed to load PDFium module" -- a failure with nothing to do
/// with the code under test (Issue #60). Windows resolves a bare `pdfium.dll`
/// through the OS search path instead, which is why CI never saw this;
/// nothing here touches that path.
///
/// The library itself is present: `flutter test` does run `pdfium_dart`'s
/// build hook, which downloads pdfium and records the result in the hook's
/// `output.json`. Reading that record back is what connects the two, and
/// keeps these tests on the real pdfium pipeline rather than a stand-in.
String? _hookBuiltPdfiumModule() {
  if (!Platform.isLinux) return null;
  final hookOutputs = Directory('.dart_tool/hooks_runner/pdfium_dart');
  if (!hookOutputs.existsSync()) return null;
  for (final run in hookOutputs.listSync().whereType<Directory>()) {
    final output = File('${run.path}/output.json');
    if (!output.existsSync()) continue;
    final decoded =
        jsonDecode(output.readAsStringSync()) as Map<String, dynamic>;
    for (final asset in decoded['assets'] as List<dynamic>? ?? const []) {
      final encoding =
          (asset as Map<String, dynamic>)['encoding'] as Map<String, dynamic>?;
      if (encoding?['id'] != 'package:pdfium_dart/libpdfium') continue;
      final file = encoding!['file'] as String?;
      if (file != null && File(file).existsSync()) return file;
    }
  }
  return null;
}

void main() {
  setUpAll(() {
    // pdfrxFlutterInitialize() otherwise calls path_provider's
    // getTemporaryDirectory() over a platform channel that `flutter test`
    // has no implementation for (MissingPluginException). Pre-setting this
    // skips that call entirely; it never actually needs a *writable* cache
    // for these fixture sizes.
    Pdfrx.cacheDirectoryPath = Directory.systemTemp.path;
    // Left untouched (and the default resolution used) wherever the loader
    // can find pdfium on its own -- see `_hookBuiltPdfiumModule`.
    final pdfiumModule = _hookBuiltPdfiumModule();
    if (pdfiumModule != null) Pdfrx.pdfiumModulePath = pdfiumModule;
  });

  testWidgets('shows a loading indicator before the shell finishes loading', (
    tester,
  ) async {
    final dependencies = AppDependencies(
      getSubmission: (_) => Completer<SubmissionResponse>().future,
      listQuestions: (_) => Completer<List<QuestionResponse>>().future,
      getSourcePdf: (_) => Completer<Uint8List>().future,
    );

    await _pumpReview(tester, dependencies);

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

    await _pumpReview(tester, dependencies);
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

    await _pumpReview(tester, dependencies);
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
          rubric: [
            RubricCriterionResponse(
              (b) => b
                ..id = 'c-1'
                ..description = '主旨'
                ..maxPoints = 3
                ..position = 0,
            ),
          ],
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

      await _pumpReview(tester, dependencies);
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
        find.byKey(const Key('rubric-criterion-c-1')),
        findsOneWidget,
        reason: 'the rubric criterion definition is shown',
      );
      expect(
        find.text('主旨（3点）'),
        findsOneWidget,
        reason:
            'rubric description and max points are shown, not just the '
            'criterion id',
      );
      expect(
        find.text('合格'),
        findsOneWidget,
        reason: "the grade's outcome for this criterion is shown",
      );

      // Both confidences are visible side by side, distinguished by their
      // numeric value + a Japanese level label -- never by color alone.
      expect(find.text('OCR文字認識信頼度: 55% (低)'), findsOneWidget);
      expect(find.text('採点信頼度: 97% (高)'), findsOneWidget);

      // Screen reader labels exist for both confidence badges, independent
      // of the visible text rendering above.
      expect(find.bySemanticsLabel('OCR文字認識信頼度 55% 低'), findsOneWidget);
      expect(find.bySemanticsLabel('採点信頼度 97% 高'), findsOneWidget);

      // 答案 and 設問 each have their own state readout, and each names its
      // own scope: the 答案's sits in the AppBar beside the 答案's name and
      // says so in words, the 設問's under the 問N heading (Issue #84).
      expect(find.byKey(const Key('review-submission-state')), findsOneWidget);
      expect(find.text('答案: 要確認'), findsOneWidget);
      expect(find.byKey(const Key('review-question-state')), findsOneWidget);

      semantics.dispose();
    },
  );

  testWidgets('高い確信度に緑チェックを付けない -- 印が付くのは低だけ (Issue #156)', (tester) async {
    // 実機再検証 #4 の実測: AI採点12件すべてが採点信頼度 >= 0.95 で、
    // 緑チェックも12件すべてに付いていた。その12件には誤った0点5件が
    // 含まれ、AI自身が「空白」と申告した3件(3件とも切り出しの誤り)は
    // ちょうど 1.00 だった。確信度は正誤を分けていない以上、
    // 「見なくてよい」と読める印を score の隣に置いてはいけない。
    final dependencies = _dependencies(
      pdfBytes: _pocA4PortraitPdf(),
      q1: _question(),
      recognitions: [_recognition(confidence: 0.55)],
      grades: [_grade(confidence: 0.97)],
    );

    await _pumpReview(tester, dependencies);
    await tester.pump();
    await _settlePdf(tester);

    // 肯定形から。画面が描けていなければ以下の否定形は何も守らない。
    expect(find.byKey(const Key('review-score')), findsOneWidget);
    expect(find.text('採点信頼度: 97% (高)'), findsOneWidget);
    expect(find.text('OCR文字認識信頼度: 55% (低)'), findsOneWidget);

    final high = tester.widget<Icon>(
      find.descendant(
        of: find.byKey(const Key('review-grading-confidence')),
        matching: find.byType(Icon),
      ),
    );
    final low = tester.widget<Icon>(
      find.descendant(
        of: find.byKey(const Key('review-recognition-confidence')),
        matching: find.byType(Icon),
      ),
    );
    expect(
      high.icon,
      isNot(Icons.check_circle),
      reason:
          '高 must not carry a tick: it vouches for a score nothing '
          'verified',
    );
    expect(
      low.icon,
      Icons.warning_amber,
      reason:
          '低 keeps its mark -- it is the one level that says a person '
          'is needed',
    );
    // 色でも太鼓判を押さない。低だけが自分の色を持つ。
    final context = tester.element(find.byKey(const Key('review-score')));
    expect(high.color, AppStatusTone.neutral.color(context));
    expect(low.color, AppStatusTone.attention.color(context));
  });

  testWidgets('AIが「解答欄は空白」と申告した0点は、その申告を本文で伴う (Issue #156)', (tester) async {
    // Issue #136 が保存していた `answer_image_finding` を画面へ通す。
    // 0点は「採点できた」ではなく「点を与えられなかった」で、切り出しが
    // 誤っていても正しくても同じ数字になる -- 見分ける材料はAI自身の
    // この申告しか残っていない。
    final dependencies = _dependencies(
      pdfBytes: _pocA4PortraitPdf(),
      q1: _question(),
      grades: [
        _grade(
          awarded: 0,
          confidence: 1.0,
          answerImageFinding: AnswerImageFinding.blank,
        ),
      ],
    );

    await _pumpReview(tester, dependencies);
    await tester.pump();
    await _settlePdf(tester);

    expect(find.text('0 / 5 点'), findsOneWidget);
    final notice = find.byKey(const Key('review-answer-image-blank'));
    expect(notice, findsOneWidget);
    final text = tester.widget<Text>(notice).data!;
    expect(text, contains('解答欄に何も書かれていない'));
    // 両義性まで言って止める。切り出しが誤っているとは言わない --
    // `blank` は本当の無記入(正しい0点)でもあり得る (#136)。
    expect(text, contains('本当に無記入ならこの0点は正しく'));
  });

  testWidgets('`answer` 申告と申告なしの点数には何も足さない (Issue #156)', (tester) async {
    // 全設問に文が付けば、#156 が畳んだ「常時点いている旗」を別の形で
    // 作り直すだけになる。実測12件のうち `blank` は3件で、残り9件は
    // ここを通る。
    for (final finding in [null, AnswerImageFinding.answer]) {
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        grades: [
          _grade(awarded: 0, confidence: 1.0, answerImageFinding: finding),
        ],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      expect(find.text('0 / 5 点'), findsOneWidget, reason: '$finding');
      expect(
        find.byKey(const Key('review-answer-image-blank')),
        findsNothing,
        reason: '$finding',
      );
    }
  });

  testWidgets('routes an annotation with no target Bounding Box to the comment '
      'fallback area instead of dropping it', (tester) async {
    final dependencies = _dependencies(
      pdfBytes: _pocA4PortraitPdf(),
      q1: _question(),
      // Matches the annotation's default `createdAt` -- needed for it to
      // count as belonging to the displayed grading attempt (P1 review).
      grades: [_grade()],
      annotations: [
        _annotation(kind: 'comment', rect: null, comment: '時制表現について確認'),
      ],
    );

    await _pumpReview(tester, dependencies);
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
      // The annotation is only shown once it belongs to a displayed grading
      // attempt (§12, P1 review) -- its default `createdAt` matches
      // `_grade()`'s own default, the same way a real `GradingJobProcessor`
      // run persists both from one shared clock read.
      grades: [_grade()],
      annotations: [_annotation(kind: 'circle', rect: mark)],
    );

    await _pumpReview(tester, dependencies);
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
      // See the unrotated case above: the annotation needs a matching
      // `_grade()` to count as belonging to the displayed attempt.
      grades: [_grade()],
      annotations: [_annotation(kind: 'circle', rect: mark)],
    );

    await _pumpReview(tester, dependencies);
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
        // An AI grade must exist before 承認 is allowed (P1 review) -- both
        // questions need one for Enter to reach question 2 below.
        grades: [
          _grade(id: 'grade-q1', questionId: 'q-1'),
          _grade(id: 'grade-q2', questionId: 'q-2'),
        ],
      );

      await _pumpReview(tester, dependencies);
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

      await _revealMaterial(tester);
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

    await _pumpReview(tester, dependencies);
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

    await _pumpReview(tester, dependencies);
    await tester.pump();
    await _settlePdf(tester);

    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('review-inspector')), findsOneWidget);
  });

  testWidgets(
    'shows AI and human recognition/grade side by side, never mislabeling '
    "a human correction's confidence as the AI's",
    (tester) async {
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        recognitions: [
          _recognition(id: 'rec-ai', text: 'AI認識結果', confidence: 0.6),
          RecognitionResponse(
            (b) => b
              ..id = 'rec-human'
              ..submissionId = 'sub-1'
              ..questionId = 'q-1'
              ..source_ = 'human'
              ..stage = 'human'
              ..text = '人が修正した結果'
              ..confidence = 1.0
              ..createdAt = DateTime.utc(2026, 1, 1, 0, 1),
          ),
        ],
        grades: [
          _grade(id: 'grade-ai', awarded: 3, maximum: 5, confidence: 0.6),
          GradeResultResponse(
            (b) => b
              ..id = 'grade-human'
              ..submissionId = 'sub-1'
              ..questionId = 'q-1'
              ..source_ = 'human'
              ..score.awarded = 5
              ..score.maximum = 5
              ..score.ratio = 1.0
              ..confidence = 1.0
              ..criteria.replace(const [])
              ..createdAt = DateTime.utc(2026, 1, 1, 0, 1),
          ),
        ],
        // A human grade only *displays* as confirmed once a `modified`
        // review is in effect for it (Issue #22 P1: Undo must actually
        // revert what is displayed) -- real data from `edit_question`
        // always carries this row alongside the human grade it produced.
        reviews: [
          _review(
            action: 'modified',
            aiGradeResultId: 'grade-ai',
            humanGradeResultId: 'grade-human',
            createdAt: DateTime.utc(2026, 1, 1, 0, 1),
          ),
        ],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      // The AI's original proposal is still visible...
      expect(find.text('AI認識結果'), findsOneWidget);
      expect(find.text('3 / 5 点'), findsOneWidget);
      // ...alongside the human correction, clearly labeled as such...
      expect(
        find.byKey(const Key('review-human-recognition-label')),
        findsOneWidget,
      );
      expect(find.text('人が修正した結果'), findsOneWidget);
      expect(find.byKey(const Key('review-human-grade-label')), findsOneWidget);
      expect(find.text('5 / 5 点'), findsOneWidget);
      // ...and the only Recognition Confidence badge shown is the AI's own
      // (60%), never a "100%" badge implying the AI was that confident.
      expect(find.text('OCR文字認識信頼度: 60% (低)'), findsOneWidget);
      expect(find.textContaining('OCR文字認識信頼度: 100%'), findsNothing);
    },
  );

  testWidgets(
    'the PDF overlay only ever shows the currently selected question, not '
    'every question ever visited on the same page',
    (tester) async {
      final markA = _rect(0.2, 0.2, 0.05, 0.05);
      final markB = _rect(0.7, 0.7, 0.05, 0.05);
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(id: 'q-1', number: '1', page: 1),
        q2: _question(id: 'q-2', number: '2', page: 1),
        // Each annotation needs a matching grade for its own question to
        // count as belonging to the displayed attempt (P1 review).
        grades: [
          _grade(id: 'grade-q1', questionId: 'q-1'),
          _grade(id: 'grade-q2', questionId: 'q-2'),
        ],
        annotations: [
          _annotation(id: 'anno-a', questionId: 'q-1', rect: markA),
          _annotation(id: 'anno-b', questionId: 'q-2', rect: markB),
        ],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      expect(find.byKey(const Key('annotation-anno-a')), findsOneWidget);
      expect(find.byKey(const Key('annotation-anno-b')), findsNothing);

      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pump();
      await _settlePdf(tester);

      expect(find.byKey(const Key('annotation-anno-a')), findsNothing);
      expect(find.byKey(const Key('annotation-anno-b')), findsOneWidget);

      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pump();
      await _settlePdf(tester);

      // Back on question 1: only its own annotation shows, not question 2's
      // as well just because it was visited in between.
      expect(find.byKey(const Key('annotation-anno-a')), findsOneWidget);
      expect(find.byKey(const Key('annotation-anno-b')), findsNothing);
    },
  );

  testWidgets('a submission stuck in ai_processing is refetched via the manual '
      'refresh action once AI results become available', (tester) async {
    var recognitionsAvailable = false;
    var submissionState = 'ai_processing';
    final dependencies = AppDependencies(
      getSubmission: (_) async => _submission(state: submissionState),
      listQuestions: (_) async => [_question()],
      getSourcePdf: (_) async => _pocA4PortraitPdf(),
      listRecognitions: (_, _) async =>
          recognitionsAvailable ? [_recognition()] : const [],
      listGrades: (_, _) async => const [],
      listAnnotations: (_, _) async => const [],
      listReviews: (_, _) async => const [],
    );

    await _pumpReview(tester, dependencies);
    await tester.pump();
    await _settlePdf(tester);

    expect(
      find.byKey(const Key('review-question-empty')),
      findsOneWidget,
      reason: 'nothing has landed for this question yet',
    );

    // AI work finishes in the background (outside this screen's control).
    recognitionsAvailable = true;
    submissionState = 'ai_processed';

    await tester.tap(find.byKey(const Key('review-refresh-button')));
    await tester.pump();
    await _settlePdf(tester);

    expect(
      find.text('光合成によって酸素が発生する'),
      findsOneWidget,
      reason:
          'manual refresh must pick up results that arrived after '
          'the initial (empty) load',
    );
    // The refreshed 答案 state lands in the AppBar, where it names its own
    // scope rather than reading as the selected 設問's (Issue #84).
    expect(find.text('答案: AI処理済み'), findsOneWidget);
  });

  testWidgets('blocks 承認/却下 while the current question is still loading or '
      'errored, so a decision is never made on unseen data', (tester) async {
    final recognitionsCompleter = Completer<List<RecognitionResponse>>();
    final dependencies = AppDependencies(
      getSubmission: (_) async => _submission(),
      listQuestions: (_) async => [_question()],
      getSourcePdf: (_) async => _pocA4PortraitPdf(),
      listRecognitions: (_, _) => recognitionsCompleter.future,
      listGrades: (_, _) async => const [],
      listAnnotations: (_, _) async => const [],
      listReviews: (_, _) async => const [],
    );

    await _pumpReview(tester, dependencies);
    await tester.pump();
    await _settlePdf(tester);

    expect(
      find.byKey(const Key('review-question-loading')),
      findsOneWidget,
      reason: 'the question fetch never resolves in this test',
    );
    final approveButton = tester.widget<FilledButton>(
      find.byKey(const Key('review-approve-button')),
    );
    final rejectButton = tester.widget<OutlinedButton>(
      find.byKey(const Key('review-reject-button')),
    );
    expect(approveButton.onPressed, isNull);
    expect(rejectButton.onPressed, isNull);

    // The keyboard shortcut must be just as inert as the disabled button.
    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pump();
    expect(find.byKey(const Key('review-question-loading')), findsOneWidget);

    recognitionsCompleter.complete(const []);
    await tester.pump();
    await tester.pump();
  });

  testWidgets(
    'the question navigation rail scrolls instead of overflowing when many '
    'questions do not fit the available height',
    (tester) async {
      addTearDown(tester.view.resetPhysicalSize);
      tester.view.physicalSize = const Size(1200, 400);
      tester.view.devicePixelRatio = 1.0;

      final questions = [
        for (var i = 1; i <= 30; i++) _question(id: 'q-$i', number: '$i'),
      ];
      final dependencies = AppDependencies(
        getSubmission: (_) async => _submission(),
        listQuestions: (_) async => questions,
        getSourcePdf: (_) async => _pocA4PortraitPdf(),
        listRecognitions: (_, _) async => const [],
        listGrades: (_, _) async => const [],
        listAnnotations: (_, _) async => const [],
        listReviews: (_, _) async => const [],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('review-question-rail')), findsOneWidget);
    },
  );

  testWidgets(
    'the narrow (stacked) layout adapts to a short viewport instead of '
    'overflowing',
    (tester) async {
      addTearDown(tester.view.resetPhysicalSize);
      tester.view.physicalSize = const Size(700, 420);
      tester.view.devicePixelRatio = 1.0;

      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        recognitions: [_recognition()],
        grades: [_grade()],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('review-inspector')), findsOneWidget);
    },
  );

  testWidgets(
    'shows the AI grade comment (総評コメント), distinct from the rationale',
    (tester) async {
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        grades: [
          _grade(rationale: '理由の説明が不足しています。', comment: '全体として要点は押さえられています。'),
        ],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      expect(find.text('理由の説明が不足しています。'), findsOneWidget);
      expect(find.byKey(const Key('review-grade-comment')), findsOneWidget);
      expect(find.text('全体として要点は押さえられています。'), findsOneWidget);
    },
  );

  testWidgets(
    'ignores the 却下 shortcut while the note field has focus, so typing '
    "'x' into it does not reject the question",
    (tester) async {
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        grades: [_grade()],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      await tester.tap(find.byKey(const Key('review-note-field')));
      await tester.pump();

      await tester.sendKeyEvent(LogicalKeyboardKey.keyX);
      await tester.pump();

      final rejectButton = tester.widget<OutlinedButton>(
        find.byKey(const Key('review-reject-button')),
      );
      // Still enabled (not mid-decision-lockout) and, more importantly,
      // the question was never actually rejected -- if the shortcut had
      // fired while typing, the rail's status icon would show "rejected".
      expect(rejectButton.onPressed, isNotNull);
      final railIcon = tester.widget<Icon>(
        find
            .descendant(
              of: find.byKey(const Key('review-question-rail')),
              matching: find.byType(Icon),
            )
            .first,
      );
      expect(railIcon.icon, isNot(Icons.cancel_outlined));
    },
  );

  testWidgets(
    'blocks 承認 until an AI grade actually exists, even once the question '
    'data has otherwise finished loading',
    (tester) async {
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        recognitions: [_recognition()],
        // No grades: recognitions/grades/annotations all resolve, so
        // hasLoaded is true, but there is still nothing to approve.
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      final approveButton = tester.widget<FilledButton>(
        find.byKey(const Key('review-approve-button')),
      );
      expect(approveButton.onPressed, isNull);

      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      await _settlePdf(tester);

      // Still on the only question -- Enter did not advance past it, which
      // it would have if approval had silently gone through.
      expect(find.text('光合成によって酸素が発生する'), findsOneWidget);
    },
  );

  testWidgets(
    'refetches a question whose cache was captured while the submission '
    'was still processing, even if a different question was open when '
    'processing actually finished',
    (tester) async {
      var submissionState = 'ai_processing';
      var q2Recognitions = <RecognitionResponse>[];
      final dependencies = AppDependencies(
        getSubmission: (_) async => _submission(state: submissionState),
        listQuestions: (_) async => [
          _question(id: 'q-1', number: '1'),
          _question(id: 'q-2', number: '2'),
        ],
        getSourcePdf: (_) async => _pocA4PortraitPdf(),
        listRecognitions: (_, questionId) async =>
            questionId == 'q-2' ? q2Recognitions : const [],
        listGrades: (_, _) async => const [],
        listAnnotations: (_, _) async => const [],
        listReviews: (_, _) async => const [],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      // Visit question 2 while still processing -- it caches an empty
      // result, marked provisional.
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pump();
      await _settlePdf(tester);
      expect(find.byKey(const Key('review-question-empty')), findsOneWidget);

      // AI work finishes while question 1 (not 2) happens to be open, and
      // question 2's answer becomes available server-side.
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pump();
      await _settlePdf(tester);
      submissionState = 'ai_processed';
      q2Recognitions = [_recognition(questionId: 'q-2', text: '設問2の答案')];
      await tester.tap(find.byKey(const Key('review-refresh-button')));
      await tester.pump();
      await _settlePdf(tester);

      // Selecting question 2 again must not show its stale, processing-time
      // empty cache -- it has to refetch now that processing has finished.
      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pump();
      await _settlePdf(tester);

      expect(
        find.text('設問2の答案'),
        findsOneWidget,
        reason:
            'question 2 must be refetched once processing has finished, '
            'not left showing its provisional empty cache forever',
      );
    },
  );

  testWidgets('clears a stale fetch error once a later silent poll succeeds', (
    tester,
  ) async {
    var listRecognitionsAttempt = 0;
    var submissionState = 'ai_processing';
    final dependencies = AppDependencies(
      getSubmission: (_) async => _submission(state: submissionState),
      listQuestions: (_) async => [_question()],
      getSourcePdf: (_) async => _pocA4PortraitPdf(),
      listRecognitions: (_, _) async {
        listRecognitionsAttempt++;
        if (listRecognitionsAttempt == 1) {
          throw SidecarApiException(SidecarErrorKind.unknown, 'boom');
        }
        return [_recognition()];
      },
      listGrades: (_, _) async => const [],
      listAnnotations: (_, _) async => const [],
      listReviews: (_, _) async => const [],
    );

    await _pumpReview(tester, dependencies);
    await tester.pump();
    await _settlePdf(tester);

    expect(find.byKey(const Key('review-question-error')), findsOneWidget);

    // The next (silent, background) poll succeeds.
    submissionState = 'ai_processed';
    await _settlePoll(tester);

    expect(
      find.byKey(const Key('review-question-error')),
      findsNothing,
      reason:
          'a successful refresh must clear the earlier failure, not '
          'leave the Inspector stuck showing it',
    );
    expect(find.text('光合成によって酸素が発生する'), findsOneWidget);
  });

  testWidgets(
    'sorts question numbers naturally (1, 2, ..., 10), not lexicographically',
    (tester) async {
      final dependencies = AppDependencies(
        getSubmission: (_) async => _submission(),
        listQuestions: (_) async => [
          _question(id: 'q-10', number: '10'),
          _question(id: 'q-2', number: '2'),
          _question(id: 'q-1', number: '1'),
        ],
        getSourcePdf: (_) async => _pocA4PortraitPdf(),
        listRecognitions: (_, _) async => const [],
        listGrades: (_, _) async => const [],
        listAnnotations: (_, _) async => const [],
        listReviews: (_, _) async => const [],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      final rail = tester.widget<NavigationRail>(
        find.byKey(const Key('review-question-rail')),
      );
      final labels = [
        for (final destination in rail.destinations)
          (destination.label as Text).data,
      ];
      expect(labels, ['問1', '問2', '問10']);
    },
  );

  testWidgets(
    'keeps question labels in a single, transitive order even when some '
    'mix digits and letters (e.g. sub-question labels)',
    (tester) async {
      final dependencies = AppDependencies(
        getSubmission: (_) async => _submission(),
        listQuestions: (_) async => [
          _question(id: 'q-10', number: '10'),
          _question(id: 'q-1a', number: '1a'),
          _question(id: 'q-2', number: '2'),
        ],
        getSourcePdf: (_) async => _pocA4PortraitPdf(),
        listRecognitions: (_, _) async => const [],
        listGrades: (_, _) async => const [],
        listAnnotations: (_, _) async => const [],
        listReviews: (_, _) async => const [],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      final rail = tester.widget<NavigationRail>(
        find.byKey(const Key('review-question-rail')),
      );
      final labels = [
        for (final destination in rail.destinations)
          (destination.label as Text).data,
      ];
      // A comparator that special-cases only pure-integer labels reports
      // 2 < 10, 10 < "1a", and "1a" < 2 all at once for this exact input --
      // a genuine total order can only produce one consistent arrangement.
      expect(labels, ['問1a', '問2', '問10']);
    },
  );

  testWidgets(
    'keeps polling for a question with no AI result yet even though the '
    'submission itself already reports ai_processed -- intake reaches that '
    'state before any per-question job exists, so it is not a signal that '
    'processing has actually finished',
    (tester) async {
      var recognitionAvailable = false;
      final dependencies = AppDependencies(
        getSubmission: (_) async => _submission(state: 'ai_processed'),
        listQuestions: (_) async => [_question()],
        getSourcePdf: (_) async => _pocA4PortraitPdf(),
        listRecognitions: (_, _) async =>
            recognitionAvailable ? [_recognition()] : const [],
        listGrades: (_, _) async => const [],
        listAnnotations: (_, _) async => const [],
        listReviews: (_, _) async => const [],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      expect(find.byKey(const Key('review-question-empty')), findsOneWidget);

      // AI work finishes in the background -- no submission-state change,
      // no manual refresh, just the recognition becoming available.
      recognitionAvailable = true;
      await _settlePoll(tester);

      expect(
        find.text('光合成によって酸素が発生する'),
        findsOneWidget,
        reason:
            'the background poll must keep running based on whether '
            "this question has a result yet, not the submission's own "
            '(already-passed) processing state',
      );
    },
  );

  testWidgets(
    'places a text-targeted annotation at the matching OCR word box, not '
    'the annotation\'s own (never-set, in real grading output) rect',
    (tester) async {
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        recognitions: [
          RecognitionResponse(
            (b) => b
              ..id = 'rec-1'
              ..submissionId = 'sub-1'
              ..questionId = 'q-1'
              ..source_ = 'ai'
              ..stage = 'ocr'
              ..text = '光合成によって酸素が発生する'
              ..confidence = 0.9
              ..boxes.add(
                BoundingBoxResponse(
                  (b) => b
                    ..text = '酸素'
                    ..x = 0.5
                    ..y = 0.5
                    ..width = 0.05
                    ..height = 0.05,
                ),
              )
              ..createdAt = DateTime.utc(2026, 1, 1),
          ),
        ],
        // Matches the annotation's default `createdAt` -- needed for it to
        // count as belonging to the displayed grading attempt (P1 review).
        grades: [_grade()],
        annotations: [
          AnnotationResponse(
            (b) => b
              ..id = 'anno-1'
              ..submissionId = 'sub-1'
              ..questionId = 'q-1'
              ..source_ = 'ai'
              ..kind = 'underline'
              ..anchorText = '酸素'
              ..createdAt = DateTime.utc(2026, 1, 1),
          ),
        ],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      // Placed on the PDF overlay (matched the OCR box), not routed to the
      // comment fallback list.
      expect(find.byKey(const Key('annotation-anno-1')), findsOneWidget);
      expect(find.text('設問コメント'), findsNothing);

      final pageOverlayPositioned = tester.widget<Positioned>(
        find.byKey(const Key('#__pageOverlay__:1')),
      );
      final pageRect = Rect.fromLTWH(
        pageOverlayPositioned.left!,
        pageOverlayPositioned.top!,
        pageOverlayPositioned.width!,
        pageOverlayPositioned.height!,
      );
      final overlayTopLeft = tester.getTopLeft(
        find.byKey(const Key('annotation-anno-1')),
      );
      final pdfViewerTopLeft = tester.getTopLeft(find.byType(PdfViewer));
      final localOffset = overlayTopLeft - pdfViewerTopLeft;

      expect(
        localOffset.dx,
        closeTo(pageRect.left + 0.5 * pageRect.width, 5.0),
      );
      expect(
        localOffset.dy,
        closeTo(pageRect.top + 0.5 * pageRect.height, 5.0),
      );
    },
  );

  testWidgets(
    'draws no mark on the answer for a shape annotation with no OCR match, '
    'and lists it under 設問コメント instead (Issue #141, §12.4)',
    (tester) async {
      final scoreArea = _rect(0.8, 0.05, 0.1, 0.1);
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: QuestionResponse(
          (b) => b
            ..id = 'q-1'
            ..testId = 'test-1'
            ..number = '1'
            ..page = 1
            ..points = 5
            ..scoringMethod = 'additive'
            ..scoreArea = scoreArea.toBuilder(),
        ),
        // Matches the annotation's default `createdAt` -- needed for it to
        // count as belonging to the displayed grading attempt (P1 review).
        grades: [_grade()],
        annotations: [
          _annotation(
            kind: 'circle',
            rect: null,
            comment: '位置が特定できない印',
          ), // no anchor_text and no OCR boxes -- nothing to match against
        ],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      // Before Issue #141 this landed on `score_area`, which Issue #120
      // derives as a band the height of the answer box -- a ○ or × stroked
      // across a quarter of the page at a position nobody knows.
      expect(find.byKey(const Key('annotation-anno-1')), findsNothing);
      expect(find.text('設問コメント'), findsOneWidget);
      expect(find.text('位置が特定できない印'), findsOneWidget);
    },
  );

  testWidgets(
    'shows both the OCR and the AI grader\'s own recognition stages side '
    'by side when the grader corrects the OCR reading',
    (tester) async {
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        recognitions: [
          _recognition(id: 'rec-ocr', text: 'OCRが読んだ文字', confidence: 0.5),
          _recognition(
            id: 'rec-grading',
            stage: 'grading',
            text: '採点AIが訂正した文字',
            confidence: 0.85,
          ),
        ],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      expect(find.text('OCRが読んだ文字'), findsOneWidget);
      expect(
        find.byKey(const Key('review-grading-recognition-label')),
        findsOneWidget,
      );
      expect(find.text('採点AIが訂正した文字'), findsOneWidget);
      expect(find.text('採点AI文字認識信頼度: 85% (中)'), findsOneWidget);
    },
  );

  testWidgets('keeps polling until a grade actually exists, even once this '
      "question's OCR recognition has already landed while its job is still "
      'running', (tester) async {
    var gradeAvailable = false;
    final dependencies = AppDependencies(
      getSubmission: (_) async => _submission(state: 'ai_processed'),
      listQuestions: (_) async => [_question()],
      getSourcePdf: (_) async => _pocA4PortraitPdf(),
      // `GradingJobProcessor.process` persists the OCR recognition in its
      // own transaction *before* ever calling the AI provider for the
      // grading half -- so this is visible well before the job (or a
      // grade) is actually done (P1 review).
      listRecognitions: (_, _) async => [_recognition()],
      listGrades: (_, _) async => gradeAvailable ? [_grade()] : const [],
      listAnnotations: (_, _) async => const [],
      listReviews: (_, _) async => const [],
      listJobs: (_) async => [
        JobResponse(
          (b) => b
            ..id = 'job-1'
            ..kind = 'grading'
            ..submissionId = 'sub-1'
            ..questionId = 'q-1'
            ..state = 'running'
            ..attempts = 1
            ..maxAttempts = 3
            ..createdAt = DateTime.utc(2026, 1, 1)
            ..updatedAt = DateTime.utc(2026, 1, 1),
        ),
      ],
    );

    await _pumpReview(tester, dependencies);
    await tester.pump();
    await _settlePdf(tester);

    // The OCR recognition is already visible, but no grade has landed --
    // 承認 must still be blocked; approving here would confirm a grade
    // that was never produced.
    expect(find.text('光合成によって酸素が発生する'), findsOneWidget);
    final approveButton = tester.widget<FilledButton>(
      find.byKey(const Key('review-approve-button')),
    );
    expect(approveButton.onPressed, isNull);

    // The grading job's AI provider call finishes in the background --
    // no submission-state change, no manual refresh, just the job
    // finally producing a grade.
    gradeAvailable = true;
    await _settlePoll(tester);

    expect(
      find.text('4 / 5 点'),
      findsOneWidget,
      reason:
          'the background poll must keep running until a grade actually '
          "exists, not stop just because this question's OCR recognition "
          'landed first',
    );
  });

  testWidgets('only overlays annotations belonging to the currently displayed '
      'grading attempt, not a superseded one from an earlier re-submission', (
    tester,
  ) async {
    final oldMark = _rect(0.2, 0.2, 0.05, 0.05);
    final newMark = _rect(0.7, 0.7, 0.05, 0.05);
    final oldAttempt = DateTime.utc(2026, 1, 1);
    final newAttempt = DateTime.utc(2026, 1, 2);
    // Two separate grading attempts (Issue #18: a re-submission under a
    // new confirmed dependency-graph version creates a second Job, and
    // therefore a second grade + a second set of annotations, without
    // ever removing the first's) -- only the newer one is the "currently
    // displayed" attempt (`displayGrade`, the latest AI grade here).
    final dependencies = _dependencies(
      pdfBytes: _pocA4PortraitPdf(),
      q1: _question(),
      grades: [
        _grade(id: 'grade-old', awarded: 2, createdAt: oldAttempt),
        _grade(id: 'grade-new', awarded: 4, createdAt: newAttempt),
      ],
      annotations: [
        _annotation(id: 'anno-old', rect: oldMark, createdAt: oldAttempt),
        _annotation(id: 'anno-new', rect: newMark, createdAt: newAttempt),
      ],
    );

    await _pumpReview(tester, dependencies);
    await tester.pump();
    await _settlePdf(tester);

    expect(find.text('4 / 5 点'), findsOneWidget); // the latest grade shown
    expect(
      find.byKey(const Key('annotation-anno-new')),
      findsOneWidget,
      reason: "only the currently displayed attempt's mark is drawn",
    );
    expect(
      find.byKey(const Key('annotation-anno-old')),
      findsNothing,
      reason: "a superseded attempt's mark must not linger on the overlay",
    );
  });

  testWidgets(
    'places a text-targeted annotation at the OCR word box mapped from the '
    "cropped answer image's coordinates into page coordinates, not the "
    "box's own (crop-relative) coordinates copied directly onto the page",
    (tester) async {
      // The answer area covers only the bottom-right quadrant of the page
      // -- asymmetric on purpose so a missed offset or a missed scale
      // would both be visible.
      final answerArea = _rect(0.5, 0.5, 0.5, 0.5);
      // Normalized against the *crop* the OCR provider actually saw, not
      // the page: dead center of the answer image, which maps onto
      // (0.75, 0.75) on the page.
      final cropRelativeBox = _rect(0.5, 0.5, 0.05, 0.05);
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(answerArea: answerArea),
        recognitions: [
          RecognitionResponse(
            (b) => b
              ..id = 'rec-1'
              ..submissionId = 'sub-1'
              ..questionId = 'q-1'
              ..source_ = 'ai'
              ..stage = 'ocr'
              ..text = '光合成によって酸素が発生する'
              ..confidence = 0.9
              ..boxes.add(
                BoundingBoxResponse(
                  (b) => b
                    ..text = '酸素'
                    ..x = cropRelativeBox.x
                    ..y = cropRelativeBox.y
                    ..width = cropRelativeBox.width
                    ..height = cropRelativeBox.height,
                ),
              )
              ..createdAt = DateTime.utc(2026, 1, 1),
          ),
        ],
        grades: [_grade()],
        annotations: [
          AnnotationResponse(
            (b) => b
              ..id = 'anno-1'
              ..submissionId = 'sub-1'
              ..questionId = 'q-1'
              ..source_ = 'ai'
              ..kind = 'underline'
              ..anchorText = '酸素'
              ..createdAt = DateTime.utc(2026, 1, 1),
          ),
        ],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      final overlay = find.byKey(const Key('annotation-anno-1'));
      expect(overlay, findsOneWidget);

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

      // page.x = area.x + box.x * area.width = 0.5 + 0.5*0.5 = 0.75
      // page.y = area.y + box.y * area.height = 0.5 + 0.5*0.5 = 0.75
      expect(
        localOffset.dx,
        closeTo(pageRect.left + 0.75 * pageRect.width, 5.0),
      );
      expect(
        localOffset.dy,
        closeTo(pageRect.top + 0.75 * pageRect.height, 5.0),
      );
    },
  );

  testWidgets(
    'keeps polling until a newer grading attempt actually finishes, even '
    "though an older attempt's grade is already cached from before a "
    're-submission',
    (tester) async {
      final oldGradeCreatedAt = DateTime.utc(2026, 1, 1);
      final newJobCreatedAt = DateTime.utc(2026, 1, 2);
      final newGradeCreatedAt = DateTime.utc(2026, 1, 3);
      var newGradeAvailable = false;
      final dependencies = AppDependencies(
        getSubmission: (_) async => _submission(state: 'ai_processed'),
        listQuestions: (_) async => [_question()],
        getSourcePdf: (_) async => _pocA4PortraitPdf(),
        listRecognitions: (_, _) async => const [],
        listGrades: (_, _) async => [
          _grade(id: 'grade-old', awarded: 2, createdAt: oldGradeCreatedAt),
          if (newGradeAvailable)
            _grade(id: 'grade-new', awarded: 5, createdAt: newGradeCreatedAt),
        ],
        listAnnotations: (_, _) async => const [],
        listReviews: (_, _) async => const [],
        // Issue #18: a re-submission under a new confirmed dependency-graph
        // version creates a second Job for the same question, created
        // after the previous attempt's grade.
        listJobs: (_) async => [
          JobResponse(
            (b) => b
              ..id = 'job-2'
              ..kind = 'grading'
              ..submissionId = 'sub-1'
              ..questionId = 'q-1'
              ..state = newGradeAvailable ? 'succeeded' : 'running'
              ..attempts = 1
              ..maxAttempts = 3
              ..createdAt = newJobCreatedAt
              ..updatedAt = newJobCreatedAt,
          ),
        ],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      // Nothing wrong with showing the previous attempt's grade while the
      // new one is still running -- the bug is failing to keep polling
      // past it.
      expect(find.text('2 / 5 点'), findsOneWidget);

      // The new attempt's AI provider call finishes in the background --
      // no manual refresh.
      newGradeAvailable = true;
      await _settlePoll(tester);

      expect(
        find.text('5 / 5 点'),
        findsOneWidget,
        reason:
            'the background poll must keep running until the new '
            "attempt's own grade actually lands, not stop just because an "
            'older grade already existed from a superseded attempt',
      );
    },
  );

  testWidgets(
    'refetches recognitions after observing a newly committed grade, so a '
    "commit landing between the recognitions and grades fetches doesn't "
    'leave the grading AI recognition permanently missing',
    (tester) async {
      var recognitionsCallCount = 0;
      final gradeCreatedAt = DateTime.utc(2026, 1, 5);
      final dependencies = AppDependencies(
        getSubmission: (_) async => _submission(state: 'ai_processed'),
        listQuestions: (_) async => [_question()],
        getSourcePdf: (_) async => _pocA4PortraitPdf(),
        // The first call races GradingJobProcessor's atomic commit and
        // only sees the OCR-stage recognition (persisted separately,
        // earlier) -- the grading-stage recognition (created alongside
        // the grade, same `created_at`) only shows up once refetched.
        listRecognitions: (_, _) async {
          recognitionsCallCount++;
          return [
            _recognition(id: 'rec-ocr', text: 'OCRが読んだ文字'),
            if (recognitionsCallCount > 1)
              _recognition(
                id: 'rec-grading',
                stage: 'grading',
                text: '採点AIが訂正した文字',
                confidence: 0.85,
                createdAt: gradeCreatedAt,
              ),
          ];
        },
        listGrades: (_, _) async => [_grade(createdAt: gradeCreatedAt)],
        listAnnotations: (_, _) async => const [],
        listReviews: (_, _) async => const [],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      expect(
        find.text('採点AIが訂正した文字'),
        findsOneWidget,
        reason:
            'a grade observed alongside a not-yet-visible grading '
            'recognition must trigger one more recognitions fetch, not '
            'leave it missing until a manual refresh',
      );
      expect(recognitionsCallCount, greaterThanOrEqualTo(2));
    },
  );

  testWidgets('places a text-targeted annotation at the OCR word box from the '
      "currently displayed grading attempt's own recognition, not a stale "
      'earlier attempt that happens to report the same text at a different '
      'position', (tester) async {
    final oldAttempt = DateTime.utc(2026, 1, 1);
    final newAttempt = DateTime.utc(2026, 1, 2);
    final oldBox = _rect(0.2, 0.2, 0.05, 0.05);
    final newBox = _rect(0.7, 0.7, 0.05, 0.05);
    // Two grading attempts (Issue #18 re-submission) whose OCR results
    // both mention the same anchor text, at different positions -- the
    // append-only recognition history keeps both, oldest first.
    final dependencies = _dependencies(
      pdfBytes: _pocA4PortraitPdf(),
      q1: _question(),
      recognitions: [
        RecognitionResponse(
          (b) => b
            ..id = 'rec-old'
            ..submissionId = 'sub-1'
            ..questionId = 'q-1'
            ..source_ = 'ai'
            ..stage = 'ocr'
            ..text = '古い試行の答案'
            ..confidence = 0.9
            ..boxes.add(
              BoundingBoxResponse(
                (b) => b
                  ..text = '酸素'
                  ..x = oldBox.x
                  ..y = oldBox.y
                  ..width = oldBox.width
                  ..height = oldBox.height,
              ),
            )
            ..createdAt = oldAttempt,
        ),
        RecognitionResponse(
          (b) => b
            ..id = 'rec-new'
            ..submissionId = 'sub-1'
            ..questionId = 'q-1'
            ..source_ = 'ai'
            ..stage = 'ocr'
            ..text = '新しい試行の答案'
            ..confidence = 0.9
            ..boxes.add(
              BoundingBoxResponse(
                (b) => b
                  ..text = '酸素'
                  ..x = newBox.x
                  ..y = newBox.y
                  ..width = newBox.width
                  ..height = newBox.height,
              ),
            )
            ..createdAt = newAttempt,
        ),
      ],
      grades: [_grade(createdAt: newAttempt)],
      annotations: [
        AnnotationResponse(
          (b) => b
            ..id = 'anno-1'
            ..submissionId = 'sub-1'
            ..questionId = 'q-1'
            ..source_ = 'ai'
            ..kind = 'underline'
            ..anchorText = '酸素'
            ..createdAt = newAttempt,
        ),
      ],
    );

    await _pumpReview(tester, dependencies);
    await tester.pump();
    await _settlePdf(tester);

    final overlay = find.byKey(const Key('annotation-anno-1'));
    expect(overlay, findsOneWidget);

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

    expect(
      localOffset.dx,
      closeTo(pageRect.left + 0.7 * pageRect.width, 5.0),
      reason:
          "must use the current attempt's own OCR box (0.7), not the "
          'superseded earlier attempt\'s (0.2)',
    );
    expect(localOffset.dy, closeTo(pageRect.top + 0.7 * pageRect.height, 5.0));
  });

  group('Issue #22: edit/reject/regrade/approve/undo', () {
    testWidgets(
      '却下 persists a Review(rejected) through the sidecar and updates the '
      'rail status icon',
      (tester) async {
        String? capturedReason;
        int? capturedExpectedVersion;
        final reviews = <ReviewResponse>[];
        final dependencies = _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          grades: [_grade()],
          reviews: reviews,
          rejectReview:
              (
                submissionId,
                questionId, {
                required expectedVersion,
                reason,
              }) async {
                capturedReason = reason;
                capturedExpectedVersion = expectedVersion;
                final review = _review(
                  questionId: questionId,
                  action: 'rejected',
                  version: expectedVersion + 1,
                  note: reason,
                );
                reviews.add(review);
                return _reviewAction(review);
              },
        );

        await _pumpReview(tester, dependencies);
        await tester.pump();
        await _settlePdf(tester);

        await tester.enterText(
          find.byKey(const Key('review-note-field')),
          '手書き文字が判読できない',
        );
        await tester.pump();

        await tester.tap(find.byKey(const Key('review-reject-button')));
        await tester.pump();
        await _settlePdf(tester);

        expect(capturedExpectedVersion, 0);
        expect(capturedReason, '手書き文字が判読できない');
        final railIcon = tester.widget<Icon>(
          find
              .descendant(
                of: find.byKey(const Key('review-question-rail')),
                matching: find.byType(Icon),
              )
              .first,
        );
        expect(railIcon.icon, Icons.cancel_outlined);
      },
    );

    testWidgets('再判定 queues a fresh AI attempt through the sidecar', (
      tester,
    ) async {
      int? capturedExpectedVersion;
      final reviews = <ReviewResponse>[];
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        grades: [_grade()],
        reviews: reviews,
        regradeReview:
            (
              submissionId,
              questionId, {
              required expectedVersion,
              reason,
            }) async {
              capturedExpectedVersion = expectedVersion;
              final review = _review(
                questionId: questionId,
                action: 'regrade_requested',
                version: expectedVersion + 1,
                regradeJobId: 'job-1',
              );
              reviews.add(review);
              return _reviewAction(review, jobId: 'job-1');
            },
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      await tester.tap(find.byKey(const Key('review-regrade-button')));
      await tester.pump();
      await _settlePdf(tester);

      expect(capturedExpectedVersion, 0);
      final railIcon = tester.widget<Icon>(
        find
            .descendant(
              of: find.byKey(const Key('review-question-rail')),
              matching: find.byType(Icon),
            )
            .first,
      );
      expect(railIcon.icon, Icons.autorenew);
    });

    testWidgets('修正 opens a dialog prefilled from the AI proposal and saves a '
        'Review(modified) through the sidecar', (tester) async {
      int? capturedScore;
      String? capturedComment;
      String? capturedText;
      // Mutable, unlike the other lists `_dependencies` takes: the fake
      // `editReview` below appends to these in place, so the refetch
      // `_performReviewAction` always runs afterwards (`listGrades`/
      // `listReviews` close over these same references) actually observes
      // the edit, the same way the real sidecar's own history would.
      final grades = [_grade(awarded: 3, maximum: 5)];
      final reviews = <ReviewResponse>[];
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        recognitions: [_recognition(text: 'AI認識結果')],
        grades: grades,
        reviews: reviews,
        editReview:
            (
              submissionId,
              questionId, {
              required expectedVersion,
              expectedAiGradeId,
              required scoreAwarded,
              required scoreMaximum,
              confidence = 1.0,
              criteria = const [],
              rationale,
              comment,
              recognizedText,
              annotations,
              note,
            }) async {
              capturedScore = scoreAwarded;
              capturedComment = comment;
              capturedText = recognizedText;
              final grade = GradeResultResponse(
                (b) => b
                  ..id = 'grade-human'
                  ..submissionId = 'sub-1'
                  ..questionId = questionId
                  ..source_ = 'human'
                  ..score.awarded = scoreAwarded
                  ..score.maximum = scoreMaximum
                  ..score.ratio = scoreAwarded / scoreMaximum
                  ..confidence = 1.0
                  ..comment = comment
                  ..criteria.replace(const [])
                  ..createdAt = DateTime.utc(2026, 1, 2),
              );
              final review = _review(
                questionId: questionId,
                action: 'modified',
                aiGradeResultId: 'grade-1',
                version: expectedVersion + 1,
                humanGradeResultId: 'grade-human',
                createdAt: DateTime.utc(2026, 1, 2),
              );
              grades.add(grade);
              reviews.add(review);
              return _reviewAction(review, grade: grade);
            },
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      await tester.tap(find.byKey(const Key('review-edit-button')));
      await tester.pumpAndSettle();

      // Prefilled from the AI proposal.
      expect(find.text('3'), findsOneWidget);
      expect(find.text('AI認識結果'), findsWidgets);

      await tester.enterText(find.byKey(const Key('edit-dialog-score')), '5');
      await tester.enterText(
        find.byKey(const Key('edit-dialog-comment')),
        'よくできています',
      );
      await tester.tap(find.byKey(const Key('edit-dialog-save')));
      await tester.pumpAndSettle();
      await _settlePdf(tester);

      expect(capturedScore, 5);
      expect(capturedComment, 'よくできています');
      expect(capturedText, 'AI認識結果');
      expect(find.text('5 / 5 点'), findsOneWidget);
    });

    testWidgets(
      '修正 clearing the recognized text field entirely submits an empty '
      'string, not null (Issue #22 P2 review, round 2)',
      (tester) async {
        String? capturedText = 'not-yet-called';
        final dependencies = _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          recognitions: [_recognition(text: 'AI認識結果(誤認識)')],
          grades: [_grade()],
          editReview:
              (
                submissionId,
                questionId, {
                required expectedVersion,
                expectedAiGradeId,
                required scoreAwarded,
                required scoreMaximum,
                confidence = 1.0,
                criteria = const [],
                rationale,
                comment,
                recognizedText,
                annotations,
                note,
              }) async {
                capturedText = recognizedText;
                return _reviewAction(
                  _review(
                    questionId: questionId,
                    action: 'modified',
                    version: expectedVersion + 1,
                    humanGradeResultId: 'grade-human',
                  ),
                );
              },
        );

        await _pumpReview(tester, dependencies);
        await tester.pump();
        await _settlePdf(tester);

        await tester.tap(find.byKey(const Key('review-edit-button')));
        await tester.pumpAndSettle();
        // Shown twice: once in the background Inspector (still visible
        // beneath the dialog's modal barrier) and once as the dialog's own
        // prefilled text field.
        expect(find.text('AI認識結果(誤認識)'), findsWidgets);

        // The reviewer deletes the (misread) AI text entirely to mark the
        // answer as blank, rather than leaving the AI's own reading in place.
        await tester.enterText(find.byKey(const Key('edit-dialog-text')), '');
        await tester.pump();
        await tester.tap(find.byKey(const Key('edit-dialog-save')));
        await tester.pumpAndSettle();
        await _settlePdf(tester);

        // Sent as `''`, not `null` -- `null` means "this edit does not touch
        // the recognized text at all", which would make the backend leave
        // the AI's own (misread) recognition as the one still in effect,
        // silently undoing the reviewer's explicit clear even though the
        // save itself reports success.
        expect(capturedText, '');
      },
    );

    testWidgets('修正 without ever touching an empty recognized-text field still '
        'submits null, not a spurious empty recognition (Issue #22 P2 review, '
        'round 2)', (tester) async {
      String? capturedText = 'not-yet-called';
      var editCalled = false;
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        // No recognition of any kind yet -- the text field starts empty.
        grades: [_grade(awarded: 3, maximum: 5)],
        editReview:
            (
              submissionId,
              questionId, {
              required expectedVersion,
              expectedAiGradeId,
              required scoreAwarded,
              required scoreMaximum,
              confidence = 1.0,
              criteria = const [],
              rationale,
              comment,
              recognizedText,
              annotations,
              note,
            }) async {
              editCalled = true;
              capturedText = recognizedText;
              return _reviewAction(
                _review(
                  questionId: questionId,
                  action: 'modified',
                  version: expectedVersion + 1,
                  humanGradeResultId: 'grade-human',
                ),
              );
            },
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      await tester.tap(find.byKey(const Key('review-edit-button')));
      await tester.pumpAndSettle();

      // Only the score is edited -- the (already-empty) recognized-text
      // field is left untouched.
      await tester.enterText(find.byKey(const Key('edit-dialog-score')), '5');
      await tester.pump();
      await tester.tap(find.byKey(const Key('edit-dialog-save')));
      await tester.pumpAndSettle();
      await _settlePdf(tester);

      expect(editCalled, isTrue);
      expect(
        capturedText,
        isNull,
        reason:
            'a question with nothing recognized yet must not gain a '
            'spurious empty-text human recognition on every score-only '
            'edit',
      );
    });

    testWidgets('修正 dialogが開いている間にregradeが完了しても、保存時に送るconcurrency '
        'tokenはdialogを開いた時点のものに固定される (Issue #22 P1 review, round 2)', (
      tester,
    ) async {
      int? capturedExpectedVersion;
      String? capturedExpectedAiGradeId = 'not-yet-called';
      var regradeCompleted = false;
      final oldGrade = _grade(
        id: 'grade-ai-old',
        awarded: 4,
        maximum: 5,
        createdAt: DateTime.utc(2026, 1, 1),
      );
      final newGrade = _grade(
        id: 'grade-ai-new',
        awarded: 2,
        maximum: 5,
        createdAt: DateTime.utc(2026, 1, 2),
      );
      final dependencies = AppDependencies(
        getSubmission: (_) async => _submission(),
        listQuestions: (_) async => [_question()],
        getSourcePdf: (_) async => _pocA4PortraitPdf(),
        listRecognitions: (_, _) async => [_recognition(text: 'AI認識結果')],
        listAnnotations: (_, _) async => const [],
        listReviews: (_, _) async => regradeCompleted
            ? [
                _review(
                  action: 'regrade_requested',
                  version: 1,
                  aiGradeResultId: 'grade-ai-old',
                  regradeJobId: 'job-1',
                  createdAt: DateTime.utc(2026, 1, 1, 12),
                ),
              ]
            : const <ReviewResponse>[],
        listGrades: (_, _) async =>
            regradeCompleted ? [oldGrade, newGrade] : [oldGrade],
        listJobs: (_) async => [
          JobResponse(
            (b) => b
              ..id = 'job-1'
              ..kind = 'grading'
              ..submissionId = 'sub-1'
              ..questionId = 'q-1'
              ..state = regradeCompleted ? 'succeeded' : 'queued'
              ..attempts = 1
              ..maxAttempts = 3
              ..createdAt = DateTime.utc(2026, 1, 1)
              ..updatedAt = regradeCompleted
                  ? DateTime.utc(2026, 1, 2)
                  : DateTime.utc(2026, 1, 1),
          ),
        ],
        editReview:
            (
              submissionId,
              questionId, {
              required expectedVersion,
              expectedAiGradeId,
              required scoreAwarded,
              required scoreMaximum,
              confidence = 1.0,
              criteria = const [],
              rationale,
              comment,
              recognizedText,
              annotations,
              note,
            }) async {
              capturedExpectedVersion = expectedVersion;
              capturedExpectedAiGradeId = expectedAiGradeId;
              return _reviewAction(
                _review(
                  questionId: questionId,
                  action: 'modified',
                  version: expectedVersion + 1,
                  humanGradeResultId: 'grade-human',
                ),
              );
            },
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);
      expect(find.text('4 / 5 点'), findsOneWidget);

      // Open the 修正 dialog while grade-ai-old (expectedVersion 0) is
      // still the displayed AI attempt.
      await tester.tap(find.byKey(const Key('review-edit-button')));
      await tester.pump();
      expect(find.byKey(const Key('edit-dialog-save')), findsOneWidget);

      // A regrade completes in the background while the dialog is still
      // open -- the background poll (a `Timer.periodic` on the fake test
      // clock, which only `tester.pump(duration)` advances) picks up the
      // fresh AI attempt and mutates the very same `QuestionReviewState`
      // the dialog was opened against, in place.
      regradeCompleted = true;
      await _settlePoll(tester);

      // Save without changing anything -- must submit the concurrency
      // tokens the dialog was actually opened with (matching the stale
      // score/text it still shows), not the ones the background poll
      // updated to while it was open; otherwise this save would silently
      // land against an AI attempt the reviewer never saw.
      await tester.tap(find.byKey(const Key('edit-dialog-save')));
      await tester.pump();
      await _settlePdf(tester);

      expect(capturedExpectedVersion, 0);
      expect(capturedExpectedAiGradeId, 'grade-ai-old');
    });

    testWidgets(
      '修正 preserves an explicitly-cleared recognition across a later, '
      'unrelated edit (Issue #22 P2 review, round 3)',
      (tester) async {
        final grades = [_grade(id: 'grade-ai', awarded: 4, maximum: 5)];
        final recognitions = [_recognition(id: 'rec-ai', text: 'AI誤認識')];
        final reviews = <ReviewResponse>[];
        var editCount = 0;
        String? secondEditRecognizedText = 'not-yet-called';
        final dependencies = _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          recognitions: recognitions,
          grades: grades,
          reviews: reviews,
          editReview:
              (
                submissionId,
                questionId, {
                required expectedVersion,
                expectedAiGradeId,
                required scoreAwarded,
                required scoreMaximum,
                confidence = 1.0,
                criteria = const [],
                rationale,
                comment,
                recognizedText,
                annotations,
                note,
              }) async {
                editCount++;
                if (editCount == 2) secondEditRecognizedText = recognizedText;
                final humanGradeId = 'grade-human-$editCount';
                final createdAt = DateTime.utc(2026, 1, editCount + 1);
                final grade = GradeResultResponse(
                  (b) => b
                    ..id = humanGradeId
                    ..submissionId = 'sub-1'
                    ..questionId = questionId
                    ..source_ = 'human'
                    ..score.awarded = scoreAwarded
                    ..score.maximum = scoreMaximum
                    ..score.ratio = scoreAwarded / scoreMaximum
                    ..confidence = 1.0
                    ..comment = comment
                    ..criteria.replace(const [])
                    ..createdAt = createdAt,
                );
                grades.add(grade);
                if (recognizedText != null) {
                  recognitions.add(
                    RecognitionResponse(
                      (b) => b
                        ..id = 'rec-human-$editCount'
                        ..submissionId = 'sub-1'
                        ..questionId = questionId
                        ..source_ = 'human'
                        ..stage = 'human'
                        ..text = recognizedText
                        ..confidence = 1.0
                        ..boxes.replace(const [])
                        ..createdAt = createdAt,
                    ),
                  );
                }
                final review = _review(
                  questionId: questionId,
                  action: 'modified',
                  aiGradeResultId: 'grade-ai',
                  humanGradeResultId: humanGradeId,
                  version: expectedVersion + 1,
                  createdAt: createdAt,
                );
                reviews.add(review);
                return _reviewAction(review, grade: grade);
              },
        );

        await _pumpReview(tester, dependencies);
        await tester.pump();
        await _settlePdf(tester);

        // First edit: clear the AI-misread text entirely (an explicit
        // clear, per the round-2 fix already tested above).
        await tester.tap(find.byKey(const Key('review-edit-button')));
        await tester.pumpAndSettle();
        await tester.enterText(find.byKey(const Key('edit-dialog-text')), '');
        await tester.tap(find.byKey(const Key('edit-dialog-save')));
        await tester.pumpAndSettle();
        await _settlePdf(tester);

        // Second, unrelated edit: change only the score, leaving the
        // (still empty, now-effective human) text field untouched.
        await tester.tap(find.byKey(const Key('review-edit-button')));
        await tester.pumpAndSettle();
        await tester.enterText(find.byKey(const Key('edit-dialog-score')), '3');
        await tester.tap(find.byKey(const Key('edit-dialog-save')));
        await tester.pumpAndSettle();
        await _settlePdf(tester);

        expect(editCount, 2);
        // Sent as `''` again, not `null` -- `null` on this second edit would
        // tell the server "this edit does not touch recognized text",
        // leaving the first edit's explicit empty correction without a
        // matching recognition for the *new* human grade this edit just
        // created, and the effective-recognition resolver would fall back
        // to displaying the original AI-misread text again.
        expect(secondEditRecognizedText, '');
      },
    );

    testWidgets(
      '修正 carries the displayed grade\'s own rubric criteria and rationale '
      'forward on a comment-only edit (Issue #22 P2 review, round 3)',
      (tester) async {
        List<CriterionOutcomeRequest>? capturedCriteria;
        String? capturedRationale = 'not-yet-called';
        final aiGrade = GradeResultResponse(
          (b) => b
            ..id = 'grade-ai'
            ..submissionId = 'sub-1'
            ..questionId = 'q-1'
            ..source_ = 'ai'
            ..score.awarded = 4
            ..score.maximum = 5
            ..score.ratio = 0.8
            ..confidence = 0.9
            ..rationale = '理由の説明が不足しています。'
            ..criteria.replace([
              CriterionResultResponse(
                (b) => b
                  ..criterionId = 'c-1'
                  ..outcome = 'pass'
                  ..confidence = 0.9,
              ),
              CriterionResultResponse(
                (b) => b
                  ..criterionId = 'c-2'
                  ..outcome = 'partial'
                  ..confidence = 0.7,
              ),
            ])
            ..createdAt = DateTime.utc(2026, 1, 1),
        );
        final dependencies = _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          grades: [aiGrade],
          editReview:
              (
                submissionId,
                questionId, {
                required expectedVersion,
                expectedAiGradeId,
                required scoreAwarded,
                required scoreMaximum,
                confidence = 1.0,
                criteria = const [],
                rationale,
                comment,
                recognizedText,
                annotations,
                note,
              }) async {
                capturedCriteria = criteria;
                capturedRationale = rationale;
                return _reviewAction(
                  _review(
                    questionId: questionId,
                    action: 'modified',
                    aiGradeResultId: 'grade-ai',
                    version: expectedVersion + 1,
                    humanGradeResultId: 'grade-human',
                  ),
                );
              },
        );

        await _pumpReview(tester, dependencies);
        await tester.pump();
        await _settlePdf(tester);

        // Only the comment field is editable-and-edited here -- the dialog
        // itself has no rubric-criteria/rationale fields at all.
        await tester.tap(find.byKey(const Key('review-edit-button')));
        await tester.pumpAndSettle();
        await tester.enterText(
          find.byKey(const Key('edit-dialog-comment')),
          'コメントのみ変更',
        );
        await tester.tap(find.byKey(const Key('edit-dialog-save')));
        await tester.pumpAndSettle();
        await _settlePdf(tester);

        expect(capturedRationale, '理由の説明が不足しています。');
        expect(capturedCriteria, isNotNull);
        expect(capturedCriteria, hasLength(2));
        expect(capturedCriteria![0].criterionId, 'c-1');
        expect(capturedCriteria![0].outcome, 'pass');
        expect(capturedCriteria![1].criterionId, 'c-2');
        expect(capturedCriteria![1].outcome, 'partial');
      },
    );

    testWidgets('承認して次へ only records a fresh Review when the question is not '
        'already confirmed -- an already-edited question just navigates', (
      tester,
    ) async {
      var approveCalls = 0;
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(id: 'q-1', number: '1'),
        q2: _question(id: 'q-2', number: '2'),
        grades: [
          _grade(id: 'grade-q1', questionId: 'q-1'),
          GradeResultResponse(
            (b) => b
              ..id = 'grade-human-q1'
              ..submissionId = 'sub-1'
              ..questionId = 'q-1'
              ..source_ = 'human'
              ..score.awarded = 5
              ..score.maximum = 5
              ..score.ratio = 1.0
              ..confidence = 1.0
              ..criteria.replace(const [])
              ..createdAt = DateTime.utc(2026, 1, 1, 0, 1),
          ),
          _grade(id: 'grade-q2', questionId: 'q-2'),
        ],
        reviews: [
          _review(
            questionId: 'q-1',
            action: 'modified',
            aiGradeResultId: 'grade-q1',
            humanGradeResultId: 'grade-human-q1',
            createdAt: DateTime.utc(2026, 1, 1, 0, 1),
          ),
        ],
        approveReview:
            (
              submissionId,
              questionId, {
              required expectedVersion,
              expectedAiGradeId,
              note,
            }) async {
              approveCalls++;
              return _reviewAction(
                _review(
                  questionId: questionId,
                  action: 'approved',
                  version: expectedVersion + 1,
                ),
              );
            },
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      expect(find.text('5 / 5 点'), findsOneWidget);

      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      await _settlePdf(tester);

      // Navigated to question 2 -- but the already-confirmed question 1
      // never triggered a second, redundant `approveReview` call.
      expect(approveCalls, 0);
      expect(find.text('4 / 5 点'), findsOneWidget);
    });

    testWidgets(
      'Ctrl+Z undoes the currently-effective review as a new row, without '
      'requiring the mouse',
      (tester) async {
        String? capturedTargetVersion;
        final reviews = [
          _review(action: 'approved', aiGradeResultId: 'grade-1'),
        ];
        final dependencies = _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          grades: [_grade()],
          reviews: reviews,
          undoReview:
              (submissionId, questionId, {required expectedVersion}) async {
                capturedTargetVersion = expectedVersion.toString();
                final review = _review(
                  questionId: questionId,
                  action: 'undone',
                  version: expectedVersion + 1,
                  undoneReviewId: 'review-1',
                );
                reviews.add(review);
                return _reviewAction(review);
              },
        );

        await _pumpReview(tester, dependencies);
        await tester.pump();
        await _settlePdf(tester);

        final railIconBefore = tester.widget<Icon>(
          find
              .descendant(
                of: find.byKey(const Key('review-question-rail')),
                matching: find.byType(Icon),
              )
              .first,
        );
        expect(railIconBefore.icon, Icons.check_circle);

        await tester.sendKeyDownEvent(LogicalKeyboardKey.control);
        await tester.sendKeyEvent(LogicalKeyboardKey.keyZ);
        await tester.sendKeyUpEvent(LogicalKeyboardKey.control);
        await tester.pump();
        await _settlePdf(tester);

        expect(capturedTargetVersion, '1');
        final railIconAfter = tester.widget<Icon>(
          find
              .descendant(
                of: find.byKey(const Key('review-question-rail')),
                matching: find.byType(Icon),
              )
              .first,
        );
        expect(railIconAfter.icon, Icons.radio_button_unchecked);
      },
    );

    testWidgets(
      'undoing a 修正 also reverts the recognized text the Inspector shows, '
      'not just the score (Issue #22 P1 review)',
      (tester) async {
        final aiCreatedAt = DateTime.utc(2026, 1, 1);
        final humanCreatedAt = DateTime.utc(2026, 1, 2);
        final humanGrade = GradeResultResponse(
          (b) => b
            ..id = 'grade-human'
            ..submissionId = 'sub-1'
            ..questionId = 'q-1'
            ..source_ = 'human'
            ..score.awarded = 5
            ..score.maximum = 5
            ..score.ratio = 1.0
            ..confidence = 1.0
            ..criteria.replace(const [])
            ..createdAt = humanCreatedAt,
        );
        final humanRecognition = RecognitionResponse(
          (b) => b
            ..id = 'rec-human'
            ..submissionId = 'sub-1'
            ..questionId = 'q-1'
            ..source_ = 'human'
            ..stage = 'human'
            ..text = '人による修正文字'
            ..confidence = 1.0
            ..boxes.replace(const [])
            ..createdAt = humanCreatedAt,
        );
        final modifiedReview = _review(
          action: 'modified',
          aiGradeResultId: 'grade-ai',
          humanGradeResultId: 'grade-human',
          createdAt: humanCreatedAt,
        );
        final reviews = [modifiedReview];
        final dependencies = _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          recognitions: [
            _recognition(id: 'rec-ai', text: 'AI認識結果', createdAt: aiCreatedAt),
            humanRecognition,
          ],
          grades: [
            _grade(id: 'grade-ai', createdAt: aiCreatedAt),
            humanGrade,
          ],
          reviews: reviews,
          undoReview:
              (submissionId, questionId, {required expectedVersion}) async {
                final review = _review(
                  questionId: questionId,
                  action: 'undone',
                  version: expectedVersion + 1,
                  undoneReviewId: modifiedReview.id,
                );
                reviews.add(review);
                return _reviewAction(review);
              },
        );

        await _pumpReview(tester, dependencies);
        await tester.pump();
        await _settlePdf(tester);

        // Before Undo: the human correction is shown as the effective
        // recognized text.
        expect(
          find.byKey(const Key('review-human-recognition-label')),
          findsOneWidget,
        );
        expect(find.text('人による修正文字'), findsOneWidget);

        await tester.sendKeyDownEvent(LogicalKeyboardKey.control);
        await tester.sendKeyEvent(LogicalKeyboardKey.keyZ);
        await tester.sendKeyUpEvent(LogicalKeyboardKey.control);
        await tester.pump();
        await _settlePdf(tester);

        // After Undo: the human correction must no longer be shown as in
        // effect, even though its row is still there (append-only history)
        // -- the Inspector falls back to the AI's own recognized text.
        expect(
          find.byKey(const Key('review-human-recognition-label')),
          findsNothing,
        );
        expect(find.text('人による修正文字'), findsNothing);
        expect(find.text('AI認識結果'), findsOneWidget);
      },
    );

    testWidgets(
      'a stale expected_version (409 conflict) surfaces a snackbar and '
      'refreshes instead of silently doing nothing',
      (tester) async {
        final dependencies = _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          grades: [_grade()],
          approveReview:
              (
                submissionId,
                questionId, {
                required expectedVersion,
                expectedAiGradeId,
                note,
              }) async {
                throw SidecarApiException(
                  SidecarErrorKind.conflict,
                  "'sub-1':'q-1': expected version 0 but the review history "
                  'is already at 1; reload and retry',
                );
              },
        );

        await _pumpReview(tester, dependencies);
        await tester.pump();
        await _settlePdf(tester);

        await tester.tap(find.byKey(const Key('review-approve-button')));
        await tester.pump();
        await _settlePdf(tester);

        expect(find.textContaining('競合しました'), findsOneWidget);
      },
    );

    testWidgets(
      'refreshing after an action targets the question the action was '
      'actually for, even if the reviewer navigated away while it was still '
      'in flight (P2 review)',
      (tester) async {
        final approveCompleter = Completer<void>();
        final reviews = <ReviewResponse>[];
        final dependencies = _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(id: 'q-1', number: '1'),
          q2: _question(id: 'q-2', number: '2'),
          recognitions: [
            _recognition(questionId: 'q-1', text: '設問1の答案'),
            _recognition(questionId: 'q-2', text: '設問2の答案'),
          ],
          grades: [
            _grade(id: 'grade-q1', questionId: 'q-1'),
            _grade(id: 'grade-q2', questionId: 'q-2'),
          ],
          reviews: reviews,
          approveReview:
              (
                submissionId,
                questionId, {
                required expectedVersion,
                expectedAiGradeId,
                note,
              }) async {
                await approveCompleter.future;
                final review = _review(
                  questionId: questionId,
                  action: 'approved',
                  version: expectedVersion + 1,
                );
                reviews.add(review);
                return _reviewAction(review);
              },
        );

        await _pumpReview(tester, dependencies);
        await tester.pump();
        await _settlePdf(tester);
        expect(find.text('設問1の答案'), findsOneWidget);

        // Start approving question 1, but its request does not resolve yet.
        await tester.tap(find.byKey(const Key('review-approve-button')));
        await tester.pump();

        // Navigate to question 2 while question 1's approve request is
        // still in flight -- navigation stays enabled during an action, only
        // question 1's own action bar is disabled for its duration.
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
        await tester.pump();
        await _settlePdf(tester);
        expect(find.text('設問2の答案'), findsOneWidget);

        // Now let question 1's approve request resolve while question 2 is
        // selected.
        approveCompleter.complete();
        await tester.pump();
        await _settlePdf(tester);

        // Navigate back to question 1: its rail icon must already reflect
        // the approval that resolved while question 2 was selected -- a
        // refresh that targeted "whichever question was current when the
        // request resolved" (question 2) instead of question 1 itself would
        // leave question 1's cache stale here.
        await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
        await tester.pump();
        await _settlePdf(tester);
        expect(find.text('設問1の答案'), findsOneWidget);

        final railIcons = tester
            .widgetList<Icon>(
              find.descendant(
                of: find.byKey(const Key('review-question-rail')),
                matching: find.byType(Icon),
              ),
            )
            .toList();
        expect(railIcons.first.icon, Icons.check_circle);
      },
    );
  });

  // ------------------------------------------------------------------ //
  // Issue #25 acceptance: desktop standard / narrow width, focus order,
  // and the accessibility labels the review screen is navigated by.
  // ------------------------------------------------------------------ //
  group('Issue #25: 受入 -- 幅・focus・accessibility label', () {
    /// Wider and narrower than `_PdfReviewPageState`'s own 900px breakpoint.
    /// `flutter test`'s default surface is 800x600, so every other test in
    /// this file has only ever exercised the narrow branch -- the standard
    /// desktop layout was never rendered at all until this group.
    const desktopStandard = Size(1440, 900);
    const desktopNarrow = Size(820, 720);

    /// Per-question Inspector text. The rail draws a label for *every*
    /// question, so `find.text('問2')` matches from the very first frame and
    /// cannot tell "moved to question 2" from "the key did nothing"
    /// (round 1 review). These strings appear only for the question that is
    /// actually selected -- the same signal the existing keyboard-navigation
    /// test above keys its assertions on.
    const q1Answer = '設問1の答案';
    const q2Answer = '設問2の答案';

    Future<void> pumpAt(
      WidgetTester tester,
      Size size, {
      ApproveReview? approveReview,
    }) async {
      await tester.binding.setSurfaceSize(size);
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await _pumpReview(
        tester,
        _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          q2: _question(id: 'q-2', number: '2'),
          recognitions: [
            _recognition(text: q1Answer),
            _recognition(id: 'rec-2', questionId: 'q-2', text: q2Answer),
          ],
          // 承認 is refused until an AI grade exists, so both questions
          // need one for Enter to do anything at all.
          grades: [
            _grade(),
            _grade(id: 'grade-2', questionId: 'q-2'),
          ],
          approveReview: approveReview,
        ),
      );
      await tester.pump();
      await _settlePdf(tester);
    }

    /// The index `NavigationRail` itself reports as selected -- widget state
    /// that must change on every arrow key, not a label that is on screen
    /// either way.
    int selectedRailIndex(WidgetTester tester) => tester
        .widget<NavigationRail>(find.byKey(const Key('review-question-rail')))
        .selectedIndex!;

    for (final (name, size) in [
      ('desktop標準幅', desktopStandard),
      ('狭幅', desktopNarrow),
    ]) {
      testWidgets('$name でレイアウトが破綻しない', (tester) async {
        await pumpAt(tester, size);

        // A RenderFlex overflow (or any other layout assertion) is reported
        // as a framework exception, which `takeException` surfaces here
        // instead of only at teardown -- so a broken layout names *which*
        // width broke it.
        expect(tester.takeException(), isNull);
        // Both layouts keep the same controls: a narrow window rearranges
        // the screen, it does not drop half of it.
        expect(find.byType(PdfViewer), findsOneWidget);
        // ...and each one is actually *on* that screen. Presence alone is
        // not enough: a control laid out past the viewport edge, or
        // collapsed to nothing, is still `findsOneWidget` while being
        // unusable, and produces no overflow exception either (round 1
        // review's "would this go red if the feature broke?").
        for (final key in const [
          'review-question-rail',
          'review-submission-state',
          'review-approve-button',
        ]) {
          final finder = find.byKey(Key(key));
          expect(finder, findsOneWidget, reason: key);
          final rect = tester.getRect(finder);
          expect(rect.width, greaterThan(0), reason: key);
          expect(rect.height, greaterThan(0), reason: key);
          expect(
            rect.left >= 0 &&
                rect.top >= 0 &&
                rect.right <= size.width &&
                rect.bottom <= size.height,
            isTrue,
            reason: '\$key is outside the \$size viewport: \$rect',
          );
        }
      });
    }

    testWidgets('狭幅でもキーボードだけで設問を移動して承認できる', (tester) async {
      final approved = <String>[];
      await pumpAt(
        tester,
        desktopNarrow,
        approveReview:
            (
              submissionId,
              questionId, {
              required expectedVersion,
              expectedAiGradeId,
              note,
            }) async {
              approved.add(questionId);
              return _reviewAction(
                _review(questionId: questionId, action: 'approved'),
              );
            },
      );

      expect(selectedRailIndex(tester), 0);
      expect(find.text(q1Answer), findsOneWidget);
      expect(find.text(q2Answer), findsNothing);

      await tester.sendKeyEvent(LogicalKeyboardKey.arrowDown);
      await tester.pump();
      await _settlePdf(tester);
      expect(selectedRailIndex(tester), 1);
      expect(find.text(q2Answer), findsOneWidget);
      expect(find.text(q1Answer), findsNothing);

      await tester.sendKeyEvent(LogicalKeyboardKey.arrowUp);
      await tester.pump();
      await _settlePdf(tester);
      expect(selectedRailIndex(tester), 0);
      expect(find.text(q1Answer), findsOneWidget);
      expect(find.text(q2Answer), findsNothing);

      // The 承認 this test's name promises: Enter must actually reach the
      // sidecar for the selected question, and advance to the next one --
      // once that question's 判断材料 has been shown (Issue #85).
      await _revealMaterial(tester);
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      await _settlePdf(tester);
      expect(approved, ['q-1']);
      expect(selectedRailIndex(tester), 1);
      expect(find.text(q2Answer), findsOneWidget);
    });

    testWidgets('主要なaccessibility labelが両方の幅で存在する', (tester) async {
      final semantics = tester.ensureSemantics();
      for (final size in [desktopStandard, desktopNarrow]) {
        await pumpAt(tester, size);

        // The PDF itself, and both confidence figures -- the three things a
        // reviewer working by screen reader needs named. The confidence
        // labels carry the level word ("高"/"中"/"低") as well as the
        // percentage, so the value is never conveyed by color alone.
        expect(find.bySemanticsLabel(RegExp('^答案PDF 問1 ページ1')), findsOneWidget);
        expect(
          find.bySemanticsLabel(RegExp('^OCR文字認識信頼度 .* [高中低]\$')),
          findsOneWidget,
        );
        expect(
          find.bySemanticsLabel(RegExp('^採点信頼度 .* [高中低]\$')),
          findsOneWidget,
        );
      }
      semantics.dispose();
    });
  });

  // ------------------------------------------------------------------ //
  // Issue #66 review (P2): the screen resolves `AppDependencies` from a
  // provider now, and `ref` throws once a `ConsumerState` is disposed. A
  // load that awaits between two of those calls must therefore not touch
  // the provider again after the reviewer has left -- a `StateError` from
  // `ref` is not a `SidecarApiException`, so nothing here would catch it
  // and it would surface as an unhandled async error.
  // ------------------------------------------------------------------ //

  group('Issue #64: 設問依存DAGの進捗表示', () {
    /// 問1 -> 問2, with the queue in whatever state [jobs] says.
    AppDependencies graphDependencies({
      required List<JobResponse> Function() jobs,
      String graphStatus = 'confirmed',
      bool graphAvailable = true,
      DependencyGraphResponse Function()? graph,
    }) => AppDependencies(
      getSubmission: (_) async => _submission(state: 'ai_processing'),
      listQuestions: (_) async => [
        _question(),
        _question(id: 'q-2', number: '2'),
      ],
      getSourcePdf: (_) async => _pocA4PortraitPdf(),
      getDependencyGraph: (_) async => graphAvailable
          ? (graph?.call() ?? _dependencyGraph(status: graphStatus))
          : throw SidecarApiException(
              SidecarErrorKind.unknown,
              'まだ分析されていません',
              statusCode: 404,
            ),
      listJobs: (_) async => jobs(),
      listRecognitions: (_, _) async => const [],
      listGrades: (_, _) async => const [],
      listAnnotations: (_, _) async => const [],
      listReviews: (_, _) async => const [],
    );

    testWidgets('draws what is running and what it is waiting on', (
      tester,
    ) async {
      await _pumpReview(
        tester,
        graphDependencies(
          jobs: () => [
            _jobFor('q-1', state: 'running', usable: null),
            _jobFor(
              'q-2',
              state: 'blocked',
              usable: null,
              blockedOnQuestionId: 'q-1',
            ),
          ],
        ),
      );
      await _settlePdf(tester);

      expect(
        tester.widget<Text>(find.byKey(const Key('dag-node-status-q-1'))).data,
        'AI処理中',
      );
      // 「何が何待ちか」 -- the question the whole panel exists to answer.
      expect(
        tester.widget<Text>(find.byKey(const Key('dag-node-status-q-2'))).data,
        '問1 待ち',
      );
      expect(find.byKey(const Key('dag-summary')), findsOneWidget);
    });

    testWidgets('an upstream finishing releases the downstream, live', (
      tester,
    ) async {
      var q1Done = false;
      await _pumpReview(
        tester,
        graphDependencies(
          jobs: () => [
            if (q1Done)
              _jobFor('q-1')
            else
              _jobFor('q-1', state: 'running', usable: null),
            if (q1Done)
              _jobFor('q-2', state: 'queued', usable: null)
            else
              _jobFor(
                'q-2',
                state: 'blocked',
                usable: null,
                blockedOnQuestionId: 'q-1',
              ),
          ],
        ),
      );
      await _settlePdf(tester);

      // The reviewer is sitting on 問1; 問2's own progress used to stop being
      // polled the moment the selected question was done, which is exactly
      // when the rest of the submission is still working.
      q1Done = true;
      await tester.pump(const Duration(seconds: 3));
      await tester.pump();
      await tester.pump(AppMotion.emphasis);

      expect(
        tester.widget<Text>(find.byKey(const Key('dag-node-status-q-2'))).data,
        '実行待ち',
      );
    });

    testWidgets('re-confirming the graph elsewhere replaces the structure, '
        'not just the job states', (tester) async {
      // Confirming a new version in テスト設定画面 cancels this submission's
      // incomplete jobs and re-issues them against it. Polling picked the new
      // jobs up, but the graph was only ever fetched once -- so the new
      // version's execution was drawn on the old version's edges, and with a
      // dependency reversed the arrows and the 「問n 待ち」 labels contradicted
      // each other (review round 2, P2).
      var version = 1;
      await _pumpReview(
        tester,
        graphDependencies(
          graph: () => version == 1
              ? _dependencyGraph()
              : _dependencyGraph(version: 2, from: 'q-2', to: 'q-1'),
          jobs: () => version == 1
              ? [
                  _jobFor('q-1'),
                  _jobFor(
                    'q-2',
                    state: 'blocked',
                    usable: null,
                    blockedOnQuestionId: 'q-1',
                  ),
                ]
              : [
                  // The superseded jobs stay behind as CANCELLED rows, which
                  // is why the refetch keys on a *higher* version rather than
                  // on any disagreement at all.
                  _jobFor('q-1', state: 'cancelled', usable: null),
                  _jobFor('q-2', state: 'cancelled', usable: null),
                  _jobFor('q-2', graphVersion: 2),
                  _jobFor(
                    'q-1',
                    state: 'blocked',
                    usable: null,
                    blockedOnQuestionId: 'q-2',
                    graphVersion: 2,
                  ),
                ],
        ),
      );
      await _settlePdf(tester);

      double xOf(String questionId) =>
          tester.getTopLeft(find.byKey(Key('dag-node-$questionId'))).dx;

      // Layers advance along +x, so which node is to the left of which *is*
      // the drawn dependency direction.
      expect(xOf('q-1'), lessThan(xOf('q-2')));
      expect(
        tester.widget<Text>(find.byKey(const Key('dag-node-status-q-2'))).data,
        '問1 待ち',
      );

      version = 2;
      await tester.pump(const Duration(seconds: 3));
      await tester.pump();
      await tester.pump(AppMotion.emphasis);

      // The job states alone would flip the labels while leaving 問1 drawn
      // upstream of 問2 -- the arrow and the label then say opposite things.
      expect(xOf('q-2'), lessThan(xOf('q-1')));
      expect(
        tester.widget<Text>(find.byKey(const Key('dag-node-status-q-1'))).data,
        '問2 待ち',
      );
      expect(
        tester.widget<Text>(find.byKey(const Key('dag-node-status-q-2'))).data,
        'レビュー待ち',
      );
    });

    testWidgets('confirming the draft the panel is refusing to draw brings '
        'the diagram back', (tester) async {
      // `DependencyGraph.confirm` does not bump the version, so a draft that
      // gets confirmed keeps its number. Waiting for a strictly newer version
      // therefore never fired, and the panel stayed on its 未確定 notice for
      // the rest of the session -- polling and 更新 alike (review round 3,
      // P2).
      var confirmed = false;
      // 問2 stays BLOCKED throughout, which is what keeps this submission
      // being polled at all.
      List<JobResponse> jobsAt(int version) => [
        _jobFor('q-1', graphVersion: version),
        _jobFor(
          'q-2',
          state: 'blocked',
          usable: null,
          blockedOnQuestionId: 'q-1',
          graphVersion: version,
        ),
      ];
      await _pumpReview(
        tester,
        graphDependencies(
          graph: () => confirmed
              ? _dependencyGraph(version: 2)
              : _dependencyGraph(status: 'draft', version: 2),
          // Before the confirm the jobs still belong to v1, which must *not*
          // provoke a refetch: a draft ahead of every job is the ordinary
          // re-analyzed-after-registration case.
          jobs: () => jobsAt(confirmed ? 2 : 1),
        ),
      );
      await _settlePdf(tester);

      expect(find.byKey(const Key('dag-unconfirmed-notice')), findsOneWidget);
      expect(find.byKey(const Key('dag-node-q-1')), findsNothing);

      confirmed = true;
      await tester.pump(const Duration(seconds: 3));
      await tester.pump();
      await tester.pump(AppMotion.emphasis);

      expect(find.byKey(const Key('dag-unconfirmed-notice')), findsNothing);
      expect(find.byKey(const Key('dag-node-q-1')), findsOneWidget);
    });

    testWidgets('a graph fetch that fails on open is retried, not abandoned', (
      tester,
    ) async {
      // The graph is fetched once with the shell. A transient failure there
      // used to be permanent for the life of the screen: the "nothing cached"
      // guard suppressed every later attempt, so the panel stayed missing
      // even though the jobs were naming a confirmed version all along
      // (review round 3, P2).
      var failing = true;
      await _pumpReview(
        tester,
        graphDependencies(
          graph: () => failing
              ? throw SidecarApiException(
                  SidecarErrorKind.unavailable,
                  'サイドカーに接続できません',
                )
              : _dependencyGraph(),
          jobs: () => [
            _jobFor('q-1'),
            _jobFor(
              'q-2',
              state: 'blocked',
              usable: null,
              blockedOnQuestionId: 'q-1',
            ),
          ],
        ),
      );
      await _settlePdf(tester);

      expect(find.byKey(const Key('dag-node-q-1')), findsNothing);
      // ...and the failure never became the screen's error state.
      expect(find.byKey(const Key('review-shell-error')), findsNothing);

      failing = false;
      await tester.pump(const Duration(seconds: 3));
      await tester.pump();
      await tester.pump(AppMotion.emphasis);

      expect(find.byKey(const Key('dag-node-q-1')), findsOneWidget);
    });

    testWidgets('a node selects its question, and follows the selection back', (
      tester,
    ) async {
      await _pumpReview(
        tester,
        graphDependencies(jobs: () => [_jobFor('q-1'), _jobFor('q-2')]),
      );
      await _settlePdf(tester);

      expect(find.text('問1'), findsWidgets);
      await tester.tap(find.byKey(const Key('dag-node-q-2')));
      await tester.pump();
      await _settlePdf(tester);

      // The Inspector's own heading is the screen's answer to "which
      // question am I on".
      expect(
        find.descendant(
          of: find.byKey(const Key('review-inspector')),
          matching: find.text('問2'),
        ),
        findsOneWidget,
      );
    });

    testWidgets('says so rather than lying when the latest graph is a draft', (
      tester,
    ) async {
      // `/dependency-graph/analyze` always starts a new DRAFT version, and
      // the sidecar only serves the latest -- so re-analyzing a registered
      // test leaves a graph no job ever ran under.
      await _pumpReview(
        tester,
        graphDependencies(
          graphStatus: 'draft',
          jobs: () => [_jobFor('q-1'), _jobFor('q-2')],
        ),
      );
      await _settlePdf(tester);

      expect(find.byKey(const Key('dag-unconfirmed-notice')), findsOneWidget);
      expect(find.byKey(const Key('dag-node-q-1')), findsNothing);
    });

    testWidgets('a test with no graph at all just has no panel', (
      tester,
    ) async {
      // A 404 here is normal, and must never become the screen's error
      // state: the reviewer's actual work does not depend on the graph.
      await _pumpReview(
        tester,
        graphDependencies(
          graphAvailable: false,
          jobs: () => [_jobFor('q-1'), _jobFor('q-2')],
        ),
      );
      await _settlePdf(tester);

      expect(find.byKey(const Key('dag-node-q-1')), findsNothing);
      expect(find.byKey(const Key('dag-unconfirmed-notice')), findsNothing);
      expect(find.byKey(const Key('review-shell-error')), findsNothing);
      expect(find.byKey(const Key('review-inspector')), findsOneWidget);
    });
  });

  group('Issue #80: ジョブが無い答案からAI採点を開始する', () {
    /// 問1 -> 問2 の確定グラフを持つテストの、ジョブが [jobs] の答案。
    AppDependencies gradingDependencies({
      required List<JobResponse> Function() jobs,
      StartGrading? startGrading,
      List<RecognitionResponse> Function()? recognitions,
      List<GradeResultResponse> Function()? grades,
    }) => AppDependencies(
      getSubmission: (_) async => _submission(state: 'ai_processed'),
      listQuestions: (_) async => [
        _question(),
        _question(id: 'q-2', number: '2'),
      ],
      getSourcePdf: (_) async => _pocA4PortraitPdf(),
      getDependencyGraph: (_) async => _dependencyGraph(),
      listJobs: (_) async => jobs(),
      startGrading:
          startGrading ?? (submissionId) async => const <JobResponse>[],
      // Read through a callback, like `jobs`, so a test can let results
      // appear at the same moment the kickoff returns.
      listRecognitions: (_, questionId) async =>
          (recognitions?.call() ?? const [])
              .where((r) => r.questionId == questionId)
              .toList(),
      listGrades: (_, questionId) async => (grades?.call() ?? const [])
          .where((g) => g.questionId == questionId)
          .toList(),
      listAnnotations: (_, _) async => const [],
      listReviews: (_, _) async => const [],
    );

    testWidgets('ジョブが1件も無い答案には「AI採点を開始」が出て、押すとジョブができる', (tester) async {
      // Issue #80 より前に取り込まれた答案、および自動起票が失敗した答案は、
      // ここが唯一の復帰口である。
      var jobs = <JobResponse>[];
      final started = <String>[];
      await _pumpReview(
        tester,
        gradingDependencies(
          jobs: () => jobs,
          startGrading: (submissionId) async {
            started.add(submissionId);
            jobs = [
              _jobFor('q-1', state: 'queued', usable: null),
              _jobFor(
                'q-2',
                state: 'blocked',
                usable: null,
                blockedOnQuestionId: 'q-1',
              ),
            ];
            return jobs;
          },
        ),
      );
      await _settlePdf(tester);

      expect(
        find.byKey(const Key('review-grading-not-started')),
        findsOneWidget,
      );
      await tester.tap(find.byKey(const Key('review-start-grading-button')));
      // `pumpAndSettle` は使えない -- 起票が通るとジョブが実行中になり、
      // 3秒ごとのポーリングが動き続けるので settle しない (Issue #64 の
      // テストと同じ理由)。
      await _pumpTimes(tester, 5);
      await tester.pump(AppMotion.emphasis);

      expect(started, ['sub-1']);
      // 起票のあとはジョブを取り直すだけで、図がそのまま動き出す。
      expect(find.byKey(const Key('review-grading-not-started')), findsNothing);
      expect(
        tester.widget<Text>(find.byKey(const Key('dag-node-status-q-1'))).data,
        '実行待ち',
      );
      expect(
        tester.widget<Text>(find.byKey(const Key('dag-node-status-q-2'))).data,
        '問1 待ち',
      );
    });

    testWidgets('起票が終わったジョブを返してきても、採点結果まで取り直す', (tester) async {
      // 起票のPOSTが返った時点でキューが既に走り終えている場合 -- 短いDAG、
      // 速いprovider、あるいは他の経路で先に起票されていた場合 --
      // ジョブだけを取り直すと、起票前に取った**空の採点結果**が残る。
      // しかも `_isAwaitingGrade` は「終端ジョブ + 採点結果なし」を
      // 「待つものは無い」と読むのでポーリングも止まり、DAGが「レビュー待ち」
      // と言っているのにインスペクタが空のまま、手動更新まで固まる
      // (review round 2, P2)。
      var jobs = <JobResponse>[];
      var graded = false;
      await _pumpReview(
        tester,
        gradingDependencies(
          jobs: () => jobs,
          recognitions: () => graded ? [_recognition()] : const [],
          // ジョブより後に作られた採点結果。`_isAwaitingGrade` が「今回の
          // 試行の結果だ」と判断できる並びにしてある。
          grades: () =>
              graded ? [_grade(createdAt: DateTime.utc(2026, 1, 2))] : const [],
          startGrading: (submissionId) async {
            graded = true;
            jobs = [_jobFor('q-1'), _jobFor('q-2')];
            return jobs;
          },
        ),
      );
      await _settlePdf(tester);

      expect(find.byKey(const Key('review-question-empty')), findsOneWidget);

      await tester.tap(find.byKey(const Key('review-start-grading-button')));
      // ポーリングは止まる（終端ジョブ + 採点結果あり）ので settle できる。
      // 止まったうえで結果が出ていることが、この修正が効いている証拠になる
      // -- 取り直していなければ、空のまま settle してしまう。
      await tester.pumpAndSettle();

      expect(
        tester.widget<Text>(find.byKey(const Key('dag-node-status-q-1'))).data,
        'レビュー待ち',
      );
      expect(
        find.text('光合成によって酸素が発生する'),
        findsOneWidget,
        reason: '起票のあと、ジョブと一緒に採点結果も取り直していること',
      );
      expect(find.byKey(const Key('review-question-empty')), findsNothing);
    });

    testWidgets('起票の前に開いておいた別の設問も、あとで選び直せば結果が出る', (tester) async {
      // 起票前に問2を開いて空の結果をキャッシュし、問1に戻って起票する。
      // 取り直すのが「選択中の設問」だけだと、問2は空のキャッシュを抱えたまま
      // で、`_isAwaitingGrade` が「終端ジョブ + 採点結果なし」を「待つものは
      // 無い」と読むため再取得もポーリングも起きず、DAGが「レビュー待ち」と
      // 言っているのに問2のインスペクタだけ空、が手動更新まで残る
      // (review round 3, P2)。
      var jobs = <JobResponse>[];
      var graded = false;
      List<GradeResultResponse> gradesFor(String questionId) => graded
          ? [
              _grade(
                id: 'grade-$questionId',
                questionId: questionId,
                createdAt: DateTime.utc(2026, 1, 2),
              ),
            ]
          : const [];
      await _pumpReview(
        tester,
        gradingDependencies(
          jobs: () => jobs,
          recognitions: () => graded
              ? [
                  _recognition(id: 'rec-q-1', questionId: 'q-1', text: '問1の答え'),
                  _recognition(id: 'rec-q-2', questionId: 'q-2', text: '問2の答え'),
                ]
              : const [],
          grades: () => [...gradesFor('q-1'), ...gradesFor('q-2')],
          startGrading: (submissionId) async {
            graded = true;
            jobs = [_jobFor('q-1'), _jobFor('q-2')];
            return jobs;
          },
        ),
      );
      await _settlePdf(tester);

      // 起票前に問2を開く -- ここで空の結果がキャッシュされる。
      await tester.tap(find.byKey(const Key('dag-node-q-2')));
      await tester.pump();
      await _settlePdf(tester);
      expect(find.byKey(const Key('review-question-empty')), findsOneWidget);

      // 問1へ戻って起票する。取り直されるのは問1だけ。
      await tester.tap(find.byKey(const Key('dag-node-q-1')));
      await tester.pump();
      await _settlePdf(tester);
      await tester.tap(find.byKey(const Key('review-start-grading-button')));
      await tester.pumpAndSettle();
      expect(find.text('問1の答え'), findsOneWidget);

      // 問2を選び直す。ここが本題 -- 空のキャッシュが残っていると空のまま。
      await tester.tap(find.byKey(const Key('dag-node-q-2')));
      await tester.pump();
      await tester.pumpAndSettle();

      expect(
        find.text('問2の答え'),
        findsOneWidget,
        reason: '起票でジョブが変わった以上、未選択だった設問のキャッシュも無効になること',
      );
      expect(find.byKey(const Key('review-question-empty')), findsNothing);
    });

    testWidgets('ジョブが1件でもあれば「AI採点を開始」は出さない', (tester) async {
      // 起票は済んでいる。ここにボタンを置くと「押せばもう一度採点される」と
      // 読めるが、実際は idempotent で何も起きない。再実行は再判定と
      // `POST /jobs/{id}/retry` の担当である。
      await _pumpReview(
        tester,
        gradingDependencies(
          jobs: () => [
            _jobFor('q-1', state: 'running', usable: null),
            _jobFor(
              'q-2',
              state: 'blocked',
              usable: null,
              blockedOnQuestionId: 'q-1',
            ),
          ],
        ),
      );
      await _settlePdf(tester);

      expect(
        find.byKey(const Key('review-start-grading-button')),
        findsNothing,
      );
      expect(find.byKey(const Key('review-grading-not-started')), findsNothing);
    });

    testWidgets('ジョブ一覧が取れていないときは「まだ開始されていません」と言わない', (tester) async {
      // ジョブが空なのは「作られていない」からとは限らない -- 取得に失敗した
      // ときも空である。区別できないものを断定しない。
      await _pumpReview(
        tester,
        AppDependencies(
          getSubmission: (_) async => _submission(state: 'ai_processed'),
          listQuestions: (_) async => [_question()],
          getSourcePdf: (_) async => _pocA4PortraitPdf(),
          getDependencyGraph: (_) async => _dependencyGraph(),
          listJobs: (_) async => throw SidecarApiException(
            SidecarErrorKind.unavailable,
            'sidecar is not reachable',
          ),
          listRecognitions: (_, _) async => const [],
          listGrades: (_, _) async => const [],
          listAnnotations: (_, _) async => const [],
          listReviews: (_, _) async => const [],
        ),
      );
      await _settlePdf(tester);

      expect(find.byKey(const Key('review-grading-not-started')), findsNothing);
      expect(
        find.byKey(const Key('review-start-grading-button')),
        findsNothing,
      );
    });

    testWidgets('起票の応答待ちのあいだに画面を離れても落ちない', (tester) async {
      // #66（破棄後の `ref.read`）、#64（画面離脱中の pending request）に
      // 続く3度目の同じ形。`_refreshJobs` の中の `mounted` チェックは
      // **呼び出し元を止めない**ので、応答後にそのまま `_loadReview` まで
      // 進み、破棄済み State へ `setState` して未処理例外になっていた
      // (review round 4)。
      final started = Completer<List<JobResponse>>();
      await _pumpReview(
        tester,
        gradingDependencies(
          jobs: () => const [],
          startGrading: (submissionId) => started.future,
        ),
      );
      await _settlePdf(tester);

      await tester.tap(find.byKey(const Key('review-start-grading-button')));
      await tester.pump();

      // 応答が返る前に画面を捨てる。
      await tester.pumpWidget(const SizedBox());
      await tester.pumpAndSettle();

      // ここで成功応答が返る。
      started.complete([_jobFor('q-1'), _jobFor('q-2')]);
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    });

    testWidgets('404 のあとは「AI採点を開始」を出さない', (tester) async {
      // 答案そのものが無いという答えは、同じ要求を投げ直しても変わらない。
      // 取込画面は再試行ボタンを出さないのに、こちらは `finally` で
      // ボタンが復活し、「答案が見つかりません」の真上から何度でも
      // 押せていた (review round 1, P2-2)。
      var attempts = 0;
      await _pumpReview(
        tester,
        gradingDependencies(
          jobs: () => const [],
          startGrading: (submissionId) async {
            attempts++;
            throw SidecarApiException(
              SidecarErrorKind.badResponse,
              'submission not found',
              statusCode: 404,
            );
          },
        ),
      );
      await _settlePdf(tester);

      await tester.tap(find.byKey(const Key('review-start-grading-button')));
      await _pumpTimes(tester, 5);

      expect(attempts, 1);
      expect(
        tester
            .widget<Text>(find.byKey(const Key('review-start-grading-error')))
            .data,
        contains('見つかりません'),
      );
      expect(
        find.byKey(const Key('review-start-grading-button')),
        findsNothing,
      );
    });

    testWidgets('確定DAGが無いときの409は理由を出すだけで、画面をエラーにしない', (tester) async {
      // レビュアーは答案・認識文字・採点を読み続けられる。グラフが無いことを
      // 画面のエラー状態にしないのと同じ扱い
      // (docs/dependency-dag-progress-view.md §1.7, §1.11)。
      await _pumpReview(
        tester,
        gradingDependencies(
          jobs: () => const [],
          startGrading: (submissionId) async => throw SidecarApiException(
            SidecarErrorKind.conflict,
            "test 'test-1' has no confirmed, up-to-date dependency graph",
            statusCode: 409,
          ),
        ),
      );
      await _settlePdf(tester);

      await tester.tap(find.byKey(const Key('review-start-grading-button')));
      await _pumpTimes(tester, 5);

      expect(
        tester
            .widget<Text>(find.byKey(const Key('review-start-grading-error')))
            .data,
        contains('設問依存関係が確定していない'),
      );
      expect(find.byKey(const Key('review-shell-error')), findsNothing);
      // もう一度押せる。押し直すのがそのまま再試行である。
      expect(
        find.byKey(const Key('review-start-grading-button')),
        findsOneWidget,
      );
      expect(find.byKey(const Key('review-question-rail')), findsOneWidget);
      expect(tester.takeException(), isNull);
    });
  });

  group('Issue #84: 同じ設問の状態を、3箇所が同じ語とアイコンで出す', () {
    /// 4 questions with a 問1 -> 問3 edge, so the diagram, the rail and the
    /// Inspector all have something to say about each of them and one of
    /// them is genuinely 前提待ち.
    ///
    /// [submissionState] is the *答案's* state, deliberately picked to
    /// contradict 問1's own state -- that contradiction, read as if it were
    /// 問1's, is Issue #84.
    AppDependencies statesDependencies({
      required List<JobResponse> jobs,
      List<ReviewResponse> reviews = const [],
      String submissionState = 'needs_review',
      // Which dependency the graph draws. A test that needs 要確認 has to
      // point this at the same question its `blocked` job names, because
      // 要確認 now means "a dependent is stuck behind this one" and the two
      // halves of that fact -- the edge and the blocked job -- come from two
      // different endpoints (Issue #156).
      String edgeFrom = 'q-1',
      String edgeTo = 'q-3',
    }) => AppDependencies(
      getSubmission: (_) async => _submission(state: submissionState),
      listQuestions: (_) async => [
        _question(),
        _question(id: 'q-2', number: '2'),
        _question(id: 'q-3', number: '3'),
        _question(id: 'q-4', number: '4'),
      ],
      getSourcePdf: (_) async => _pocA4PortraitPdf(),
      getDependencyGraph: (_) async =>
          _dependencyGraph(from: edgeFrom, to: edgeTo),
      listJobs: (_) async => jobs,
      listRecognitions: (_, _) async => const [],
      listGrades: (_, _) async => const [],
      listAnnotations: (_, _) async => const [],
      listReviews: (submissionId, questionId) async =>
          reviews.where((r) => r.questionId == questionId).toList(),
    );

    /// The one assertion this Issue exists for: for [number], the DAG node,
    /// the rail destination and (when it is the selected question) the
    /// Inspector badge all say [label] -- and none of them says anything
    /// else about it.
    void expectAllThreeSay(
      WidgetTester tester, {
      required String questionId,
      required String number,
      required String label,
      bool selected = false,
    }) {
      expect(
        tester
            .widget<Text>(find.byKey(Key('dag-node-status-$questionId')))
            .data,
        label,
        reason: 'DAGパネルの問$number',
      );
      // The rail is too narrow for a second line, so its copy of the word
      // rides on the semantics label (and the same string as a tooltip).
      expect(
        find.bySemanticsLabel('問$number $label'),
        findsOneWidget,
        reason: '左レールの問$number',
      );
      if (selected) {
        expect(
          tester
              .widget<Text>(
                find.descendant(
                  of: find.byKey(const Key('review-question-state')),
                  matching: find.byType(Text),
                ),
              )
              .data,
          label,
          reason: '右パネルの問$number',
        );
      }
    }

    /// 問1 is 承認済み to the pipeline while the 答案 as a whole is
    /// `needs_review` -- the `pdf-review-blocked` screenshot, where the DAG
    /// said 承認済み and the badge under the 問1 heading said ⚠要確認.
    testWidgets('承認済みの設問に、答案の「要確認」が重ならない', (tester) async {
      final semantics = tester.ensureSemantics();
      await _pumpReview(
        tester,
        statesDependencies(
          submissionState: 'needs_review',
          jobs: [
            _jobFor('q-1'),
            _jobFor('q-2', state: 'succeeded', usable: false),
            _jobFor(
              'q-3',
              state: 'blocked',
              usable: null,
              blockedOnQuestionId: 'q-1',
            ),
            _jobFor('q-4'),
          ],
          reviews: [_review(action: 'approved')],
        ),
      );
      await _settlePdf(tester);

      expectAllThreeSay(
        tester,
        questionId: 'q-1',
        number: '1',
        label: '承認済み',
        selected: true,
      );
      // 要確認 is still on screen -- it is the *答案's* state, in the AppBar,
      // and it names its own scope there.
      expect(find.text('答案: 要確認'), findsOneWidget);
      // ...and nowhere near the 問1 heading any more.
      expect(
        find.descendant(
          of: find.byKey(const Key('review-inspector')),
          matching: find.textContaining('要確認'),
        ),
        findsNothing,
      );

      semantics.dispose();
    });

    /// The `pdf-review-failed` screenshot: the DAG said レビュー待ち while
    /// the badge under the same 問1 heading said ✓AI処理済み.
    testWidgets('レビュー待ちの設問に、答案の「AI処理済み」が重ならない', (tester) async {
      final semantics = tester.ensureSemantics();
      await _pumpReview(
        tester,
        statesDependencies(
          submissionState: 'ai_processed',
          jobs: [
            _jobFor('q-1'),
            _jobFor('q-2', state: 'failed', usable: false),
            _jobFor(
              'q-3',
              state: 'blocked',
              usable: null,
              blockedOnQuestionId: 'q-1',
            ),
            _jobFor('q-4'),
          ],
        ),
      );
      await _settlePdf(tester);

      expectAllThreeSay(
        tester,
        questionId: 'q-1',
        number: '1',
        label: 'レビュー待ち',
        selected: true,
      );
      expect(find.text('答案: AI処理済み'), findsOneWidget);
      expect(
        find.descendant(
          of: find.byKey(const Key('review-inspector')),
          matching: find.textContaining('AI処理済み'),
        ),
        findsNothing,
      );

      semantics.dispose();
    });

    testWidgets('未訪問の設問も、レールとDAGが同じ状態を出す', (tester) async {
      final semantics = tester.ensureSemantics();
      await _pumpReview(
        tester,
        statesDependencies(
          edgeFrom: 'q-2',
          jobs: [
            _jobFor('q-1'),
            // 要確認: succeeded, but the queue judged its own result not
            // usable, and 問3 below is stuck behind it -- so 「下流を解放
            // しなかった」 is a statement about something (Issue #156).
            _jobFor('q-2', state: 'succeeded', usable: false),
            _jobFor(
              'q-3',
              state: 'blocked',
              usable: null,
              blockedOnQuestionId: 'q-2',
            ),
            _jobFor('q-4', state: 'running', usable: null),
          ],
        ),
      );
      await _settlePdf(tester);

      // Only 問1 has ever been fetched by this screen; 問2〜問4 are drawn
      // from `listJobs`, which covers the whole submission. Before Issue #84
      // the rail had no access to any of this and drew all three as one
      // hourglass.
      expectAllThreeSay(tester, questionId: 'q-2', number: '2', label: '要確認');
      expectAllThreeSay(
        tester,
        questionId: 'q-3',
        number: '3',
        // A blocked question names its prerequisite in all three places --
        // and, since Issue #86, says whether that prerequisite is going to
        // release on its own. 問2 here is 要確認, so it will not: 問3 moves
        // when a person looks at 問2, not when the queue gets round to it.
        label: '問2 確認待ち',
      );
      expectAllThreeSay(tester, questionId: 'q-4', number: '4', label: 'AI処理中');

      semantics.dispose();
    });

    testWidgets('待っている設問が無ければ、usable=false でも要確認にしない (Issue #156)', (
      tester,
    ) async {
      // 実機再検証 #4 では、点数が作られた12件のうち11件が usable=false で、
      // そのすべてに要確認が立っていた。ところが同じ実行の依存グラフの
      // エッジは**0本**で、11件は1つも下流を止めていない。
      // `Job.usable` が決めるのは「後続の依存設問へ進んでよいか」であって
      // 「この設問を人間が見なくてよいか」ではない
      // (docs/ai-grading-pipeline.md)。誰も待っていないなら、この設問は
      // ほかの採点済みと同じ「レビュー待ち」である。
      final semantics = tester.ensureSemantics();
      await _pumpReview(
        tester,
        statesDependencies(
          jobs: [
            _jobFor('q-1'),
            _jobFor('q-2', state: 'succeeded', usable: false),
            // 問3 は問1 待ちで、問2 を待ってはいない。
            _jobFor(
              'q-3',
              state: 'blocked',
              usable: null,
              blockedOnQuestionId: 'q-1',
            ),
            _jobFor('q-4'),
          ],
        ),
      );
      await _settlePdf(tester);

      // 肯定形が先。画面が描けていないまま否定形だけ通るのを防ぐ
      // (`docs/quality-gates.md`)。
      expectAllThreeSay(
        tester,
        questionId: 'q-1',
        number: '1',
        label: 'レビュー待ち',
        selected: true,
      );
      expectAllThreeSay(tester, questionId: 'q-3', number: '3', label: '問1 待ち');

      // そのうえで、usable=false の問2 が問1 と同じ語で出る。
      expectAllThreeSay(
        tester,
        questionId: 'q-2',
        number: '2',
        label: 'レビュー待ち',
      );
      // 「要確認」がこの画面のどこにも残っていない -- 答案そのものの状態
      // (AppBar の「答案: 要確認」) は別の主語なので、そちらは統べない。
      expect(
        find.descendant(
          of: find.byKey(const Key('review-question-rail')),
          matching: find.textContaining('要確認'),
        ),
        findsNothing,
      );

      semantics.dispose();
    });

    testWidgets('レールのアイコンが状態ごとに違う (色を外しても区別できる)', (tester) async {
      await _pumpReview(
        tester,
        statesDependencies(
          edgeFrom: 'q-2',
          jobs: [
            _jobFor('q-1'),
            _jobFor('q-2', state: 'succeeded', usable: false),
            _jobFor(
              'q-3',
              state: 'blocked',
              usable: null,
              blockedOnQuestionId: 'q-2',
            ),
            _jobFor('q-4', state: 'running', usable: null),
          ],
        ),
      );
      await _settlePdf(tester);

      final rail = find.byKey(const Key('review-question-rail'));
      final icons = tester
          .widgetList<Icon>(
            find.descendant(of: rail, matching: find.byType(Icon)),
          )
          .map((icon) => icon.icon)
          .toList();
      // Four questions in four different states must produce four different
      // shapes: 要確認・前提待ち・レビュー待ち・AI処理中 all used to render
      // as `hourglass_empty`.
      expect(icons, hasLength(4));
      expect(icons.toSet(), hasLength(4));
    });

    testWidgets('狭幅でも設問番号が消えない', (tester) async {
      await tester.binding.setSurfaceSize(const Size(700, 720));
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await _pumpReview(
        tester,
        statesDependencies(
          jobs: [
            _jobFor('q-1'),
            _jobFor('q-2'),
            _jobFor('q-3', usable: false),
            _jobFor('q-4'),
          ],
        ),
      );
      await _settlePdf(tester);

      expect(tester.takeException(), isNull);
      final rail = find.byKey(const Key('review-question-rail'));
      for (final number in const ['1', '2', '3', '4']) {
        final label = find.descendant(
          of: rail,
          matching: find.text('問$number'),
        );
        expect(label, findsOneWidget, reason: '問$number');
        expect(tester.getRect(label).width, greaterThan(0));
      }
    });
  });

  group('Issue #66: leaving the screen mid-request', () {
    testWidgets('a pending shell load does not throw once the page is gone', (
      tester,
    ) async {
      // `_loadShell` calls getSubmission -> listQuestions -> getSourcePdf in
      // sequence; hold the middle one open across the dispose.
      final questions = Completer<List<QuestionResponse>>();
      final dependencies = AppDependencies(
        getSubmission: (submissionId) async => _submission(),
        listQuestions: (testId) => questions.future,
        getSourcePdf: (submissionId) async => _pocA4PortraitPdf(),
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();

      await tester.pumpWidget(const SizedBox());
      await tester.pumpAndSettle();

      questions.complete([_question()]);
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    });

    testWidgets(
      'a pending question load does not throw once the page is gone',
      (tester) async {
        // Same for `_loadReview`: listRecognitions -> listGrades -> ... ->
        // listReviews, with only one `mounted` check after all of them.
        final grades = Completer<List<GradeResultResponse>>();
        final dependencies = AppDependencies(
          getSubmission: (submissionId) async => _submission(),
          listQuestions: (testId) async => [_question()],
          getSourcePdf: (submissionId) async => _pocA4PortraitPdf(),
          listJobs: (submissionId) async => const [],
          listRecognitions: (submissionId, questionId) async => const [],
          listGrades: (submissionId, questionId) => grades.future,
          listAnnotations: (submissionId, questionId) async => const [],
          listReviews: (submissionId, questionId) async => const [],
        );

        await _pumpReview(tester, dependencies);
        await _settlePdf(tester);

        await tester.pumpWidget(const SizedBox());
        await tester.pumpAndSettle();

        grades.complete(const []);
        await tester.pumpAndSettle();

        expect(tester.takeException(), isNull);
      },
    );
  });

  // ------------------------------------------------------------------ //
  // Issue #85 acceptance: the 判断材料 承認 is a decision about, and the
  // button that takes that decision, on the same screen -- at both widths
  // the screenshots in Issue #71 were taken at.
  // ------------------------------------------------------------------ //
  group('Issue #85: 受入 -- 判断材料と承認が同じ画面にある', () {
    /// The two sizes Issue #71's evaluation material was captured at, and
    /// the two Issue #85 states its acceptance criteria in.
    const desktopStandard = Size(1280, 720);
    const desktopNarrow = Size(700, 720);

    /// 問1..問5 with 問2→問3→問5 and 問4→問5: three execution layers of the
    /// same shape as the captured screenshots, so the panel's band is the
    /// size it actually is in front of a reviewer rather than the smallest
    /// one a test could get away with.
    DependencyGraphResponse fiveQuestionGraph() => DependencyGraphResponse(
      (b) => b
        ..id = 'graph-1'
        ..testId = 'test-1'
        ..version = 1
        ..status = 'confirmed'
        ..questionIds.replace(const ['q-1', 'q-2', 'q-3', 'q-4', 'q-5'])
        ..edges.replace([
          for (final (from, to) in const [
            ('q-2', 'q-3'),
            ('q-3', 'q-5'),
            ('q-4', 'q-5'),
          ])
            DependencyEdgeModel(
              (e) => e
                ..fromQuestionId = from
                ..toQuestionId = to
                ..rationale = '前の設問の結論を使う'
                ..provides.replace(const <DependencyProvision>[]),
            ),
        ])
        ..unresolved.replace(const <UnresolvedQuestionModel>[])
        ..createdAt = DateTime.utc(2026, 1, 1)
        ..confirmedAt = DateTime.utc(2026, 1, 1),
    );

    /// Everything 承認 is a decision about, at the length the demo data
    /// (`scripts/seed-demo-app-data.py`) produces: recognized text, a score,
    /// a rationale, a 総評コメント and a two-criterion rubric with an
    /// outcome on each.
    AppDependencies reviewableQuestion({
      String rationale = '（デモ）採点根拠の文がここに入ります。',
      String comment = '（デモ）総評コメントがここに入ります。',
      int criterionCount = 2,
      List<JobResponse> jobs = const [],
      DateTime? gradeCreatedAt,
      ApproveReview? approveReview,
    }) {
      final rubric = [
        for (var i = 1; i <= criterionCount; i++)
          RubricCriterionResponse(
            (b) => b
              ..id = 'c-$i'
              ..description = '採点基準$iの説明がここに入ります'
              ..maxPoints = 1
              ..position = i - 1,
          ),
      ];
      return _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(rubric: rubric),
        recognitions: [_recognition(text: '（デモ）問1 の答案として読み取った文字列がここに入ります。')],
        grades: [
          _grade(
            rationale: rationale,
            comment: comment,
            createdAt: gradeCreatedAt,
            criteria: [
              for (final criterion in rubric)
                CriterionResultResponse(
                  (b) => b
                    ..criterionId = criterion.id
                    ..outcome = 'pass'
                    ..confidence = 0.9,
                ),
            ],
          ),
        ],
        graph: fiveQuestionGraph(),
        jobs: jobs,
        approveReview: approveReview,
      );
    }

    Future<void> pumpAt(
      WidgetTester tester,
      Size size,
      AppDependencies dependencies,
    ) async {
      await tester.binding.setSurfaceSize(size);
      addTearDown(() => tester.binding.setSurfaceSize(null));
      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);
    }

    /// Fails naming the widget, rather than leaving a bare rect comparison
    /// for a later reader to decode.
    void expectWithin(WidgetTester tester, Size size, String key) {
      final finder = find.byKey(Key(key));
      expect(finder, findsOneWidget, reason: key);
      final rect = tester.getRect(finder);
      expect(rect.height, greaterThan(0), reason: key);
      expect(
        rect.top >= 0 && rect.bottom <= size.height,
        isTrue,
        reason: '$key is outside the $size viewport: $rect',
      );
    }

    testWidgets('1280x720 で認識文字・点数・根拠・コメント・基準ごとの判定が承認ボタンと'
        '同じ画面内に収まる', (tester) async {
      await pumpAt(tester, desktopStandard, reviewableQuestion());

      expect(tester.takeException(), isNull);
      for (final key in const [
        'review-recognition-text',
        'review-score',
        'review-rationale',
        'review-grade-comment',
        'rubric-criterion-c-1',
        'rubric-criterion-c-2',
        'review-approve-button',
      ]) {
        expectWithin(tester, desktopStandard, key);
      }
      // Every 判断材料 row was on screen, so the 承認 gate never closes and
      // the reviewer is not asked to scroll for material already in front of
      // them. This content is deliberately longer than the demo seed's
      // (`scripts/seed-demo-app-data.py` writes no 総評コメント and shorter
      // 採点基準), and it still fits 1280x720.
      //
      // Not asserted on `maxScrollExtent`: the panel also carries 修正コメント
      // 欄, which is an input rather than 判断材料, so the panel may scroll a
      // little without any of the material being off screen.
      expect(
        find.byKey(const Key('review-unread-material-notice')),
        findsNothing,
      );
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNotNull,
      );
    });

    testWidgets('1280x720 で進捗パネルはInspectorの高さを奪わない', (tester) async {
      await pumpAt(tester, desktopStandard, reviewableQuestion());

      // The band is charged to the PDF viewer's pane: the Inspector and the
      // question rail beside it still start at the top of the body and run
      // to the action bar, while the viewer starts below the band.
      final inspector = tester.getRect(
        find.byKey(const Key('review-inspector')),
      );
      final rail = tester.getRect(
        find.byKey(const Key('review-question-rail')),
      );
      final viewer = tester.getRect(find.byType(PdfViewer));
      expect(inspector.top, rail.top);
      expect(
        viewer.top,
        greaterThan(inspector.top),
        reason: 'the 進捗 band sits above the viewer, not above everything',
      );
      expect(
        inspector.height,
        greaterThan(viewer.height),
        reason:
            'the band is charged to the viewer; full-width above everything, '
            'both panes would have lost the same height to it',
      );
    });

    testWidgets('進捗パネルの縦占有は画面高に応じて変わる', (tester) async {
      double bandHeight(WidgetTester tester) {
        final viewer = tester.getRect(find.byType(PdfViewer));
        final rail = tester.getRect(
          find.byKey(const Key('review-question-rail')),
        );
        return viewer.top - rail.top;
      }

      await pumpAt(tester, const Size(1280, 1000), reviewableQuestion());
      final tall = bandHeight(tester);

      await tester.binding.setSurfaceSize(desktopStandard);
      await tester.pump();
      await _settlePdf(tester);
      final short = bandHeight(tester);

      expect(tester.takeException(), isNull);
      expect(
        short,
        lessThan(tall),
        reason: 'a fixed band would cost the same 320px at either height',
      );
    });

    testWidgets('標準幅でノードが左に寄らず、帯の中央に置かれる', (tester) async {
      await pumpAt(tester, desktopStandard, reviewableQuestion());

      final band = tester.getRect(find.byKey(const Key('dag-edges')));
      final viewer = tester.getRect(find.byType(PdfViewer));
      final leftGap = band.left - viewer.left;
      final rightGap = viewer.right - band.right;
      expect(
        (leftGap - rightGap).abs(),
        lessThan(1),
        reason: 'left $leftGap vs right $rightGap: the diagram hugged one edge',
      );
      // ...and it is not a token gesture: the diagram spreads across most of
      // the band rather than sitting in the left three fifths of it.
      expect(band.width / viewer.width, greaterThan(0.6));
    });

    testWidgets('700x720 で下部の操作列が見切れず、「元に戻す」が完全に読める', (tester) async {
      await pumpAt(tester, desktopNarrow, reviewableQuestion());

      expect(tester.takeException(), isNull);
      for (final key in const [
        'review-undo-button',
        'review-regrade-button',
        'review-edit-button',
        'review-reject-button',
        'review-approve-button',
      ]) {
        expectWithin(tester, desktopNarrow, key);
      }
      // The label itself, not just the button's box: the old horizontal
      // scroll view left the button in the tree at full width with its
      // leading edge clipped off the screen, which every "is it there?"
      // assertion passes.
      final label = find.text('元に戻す (Ctrl+Z)');
      expect(label, findsOneWidget);
      final rect = tester.getRect(label);
      expect(
        rect.left >= 0 && rect.right <= desktopNarrow.width,
        isTrue,
        reason: '「元に戻す」 is clipped by the viewport: $rect',
      );
    });

    testWidgets('収まっているときはゲートが最初から解けていて、スクロールを求めない', (tester) async {
      final approved = <String>[];
      final dependencies = reviewableQuestion(
        approveReview:
            (
              submissionId,
              questionId, {
              required expectedVersion,
              expectedAiGradeId,
              note,
            }) async {
              approved.add(questionId);
              return _reviewAction(
                _review(questionId: questionId, action: 'approved'),
              );
            },
      );
      // Deliberately taller than 720 as well as wide: this test is about the
      // gate, not about whether this particular content happens to fit, and a
      // panel with nothing below its fold must never ask for a scroll.
      await pumpAt(tester, const Size(1280, 1000), dependencies);

      final inspector = tester.state<ScrollableState>(
        find
            .descendant(
              of: find.byKey(const Key('review-inspector')),
              matching: find.byType(Scrollable),
            )
            .first,
      );
      expect(
        inspector.position.maxScrollExtent,
        0,
        reason: 'the premise of this test: there is nothing to scroll to',
      );
      expect(
        find.byKey(const Key('review-unread-material-notice')),
        findsNothing,
      );
      expect(
        find.byKey(const Key('review-reveal-material-button')),
        findsNothing,
      );

      // Enter approves on the first press, with no scrolling of any kind in
      // between. Anything else is the gate taxing the ordinary case.
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      await _settlePdf(tester);
      expect(approved, ['q-1']);
    });

    testWidgets('判断材料が画面外に残っているあいだは承認もEnterも通らない', (tester) async {
      // A rubric long enough that no window height would show all of it --
      // the case the layout alone cannot fix, and the reason the gate
      // exists at all.
      await pumpAt(
        tester,
        desktopStandard,
        reviewableQuestion(criterionCount: 24),
      );

      expect(
        find.byKey(const Key('review-unread-material-notice')),
        findsOneWidget,
      );
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNull,
      );

      // The keyboard shortcut is exactly as inert as the button: pressing
      // Enter must not confirm a grade whose 基準ごとの判定 is off screen.
      await tester.sendKeyEvent(LogicalKeyboardKey.enter);
      await tester.pump();
      await _settlePdf(tester);
      final railIcons = tester
          .widgetList<Icon>(
            find.descendant(
              of: find.byKey(const Key('review-question-rail')),
              matching: find.byType(Icon),
            ),
          )
          .toList();
      expect(railIcons.first.icon, isNot(Icons.check_circle));

      // 却下 stays available throughout: refusing the AI's answer is not a
      // decision that can go wrong for want of having read it.
      expect(
        tester
            .widget<OutlinedButton>(
              find.byKey(const Key('review-reject-button')),
            )
            .onPressed,
        isNotNull,
      );
      // ...and that Enter press was not silence: it said why, and brought the
      // next screenful up, which is also the only route a keyboard-only
      // reviewer has to it (↑/↓ are 設問移動 here).
      expect(find.byType(SnackBar), findsOneWidget);
      expect(find.textContaining('判断材料が画面外に残っていました'), findsOneWidget);
      await tester.pumpAndSettle();

      // One press is one page, not the whole panel: with a rubric this long
      // the reviewer has more to read, and the gate is still closed.
      expect(
        find.byKey(const Key('review-unread-material-notice')),
        findsOneWidget,
      );
      // Reading the rest of it does open the gate.
      await _revealMaterial(tester);
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNotNull,
      );
    });

    // ---------------------------------------------------------------- //
    // レビュー1回目 P2: 初期表示だけを見ていると、ゲートが自分の出した
    // 誘導行を「未読」の根拠にしてしまう循環を見逃す。状態が変わる経路を
    // 通す。
    // ---------------------------------------------------------------- //
    testWidgets('狭幅で発動したゲートは、標準幅に広げて収まれば解ける', (tester) async {
      // 700x720 では判断材料が下端外に残る。
      await pumpAt(tester, desktopNarrow, reviewableQuestion());
      expect(
        find.byKey(const Key('review-unread-material-notice')),
        findsOneWidget,
        reason: 'the premise: the gate is closed at this width',
      );

      // 1280x720 なら収まる幅である。誘導行そのものが場所を取っていると、
      // 「収まらないから誘導行が出る／誘導行が出ているから収まらない」で
      // 固まる。
      await tester.binding.setSurfaceSize(desktopStandard);
      await tester.pump();
      await _settlePdf(tester);

      expect(
        find.byKey(const Key('review-unread-material-notice')),
        findsNothing,
        reason: 'the notice was counting itself as unread material',
      );
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNotNull,
      );
    });

    testWidgets('レイアウトを変えるだけでは既読は消えない', (tester) async {
      // A long 根拠 on purpose. At 700x720 the Inspector is stacked under the
      // viewer and spans the window; at 1280x720 it is a 440px column beside
      // it. The *same* sentences therefore wrap onto more lines at the wider
      // window, and the material gets taller as the window grows -- which is
      // exactly the case a height-based record reads as "new material".
      await pumpAt(
        tester,
        desktopNarrow,
        reviewableQuestion(
          rationale:
              '（デモ）採点根拠の文がここに入ります。設問の要求に照らして、答案のどの記述が'
              '加点対象になり、どの記述が不足しているのかを、採点基準の項目ごとに'
              '具体的に述べた、折り返しの起きる長さの文章です。',
        ),
      );
      await _revealMaterial(tester);
      expect(
        find.byKey(const Key('review-unread-material-notice')),
        findsNothing,
        reason: 'the premise: it has been read to the end',
      );

      // One test rather than one per axis. Three false positives were found
      // one axis at a time -- widening, shortening, typing -- and a fourth
      // (widening *after* reading at a narrow width, where the same sentences
      // rewrap onto fewer lines) came from the axis none of those covered.
      // Adding axes one at a time was always going to trail the next one, so
      // this asserts the general property instead: **判断材料が変わっていない
      // 限り、どう並べ直しても既読は消えない。**
      Future<void> expectStillRead(String change) async {
        await tester.pump();
        await _settlePdf(tester);
        expect(
          tester
              .widget<FilledButton>(
                find.byKey(const Key('review-approve-button')),
              )
              .onPressed,
          isNotNull,
          reason: '$change un-saw material that has not changed',
        );
        expect(
          find.byKey(const Key('review-unread-material-notice')),
          findsNothing,
          reason: '$change brought the notice back',
        );
      }

      for (final (change, size) in const [
        (
          'widening the window (the Inspector becomes a 440px column, so the '
              'same text rewraps onto more lines)',
          Size(1280, 720),
        ),
        ('shortening the window', Size(1280, 560)),
        (
          'narrowing back (the Inspector spans the window again)',
          Size(700, 720),
        ),
        ('widening and growing', Size(1600, 900)),
      ]) {
        await tester.binding.setSurfaceSize(size);
        await expectStillRead(change);
      }

      // Not a window change, but the same class of thing: the pinned
      // 修正コメント field growing shrinks the Inspector's viewport.
      await tester.enterText(
        find.byKey(const Key('review-note-field')),
        '1行目\n2行目\n3行目',
      );
      await expectStillRead('typing three lines into 修正コメント');

      // ...and scrolling back up to re-read something is not un-reading it.
      await tester.drag(
        find.byKey(const Key('review-inspector')),
        const Offset(0, 600),
      );
      await expectStillRead('scrolling back to the top');
    });

    testWidgets('build を伴わないレイアウト変更でも、末尾判定は測り直される', (tester) async {
      // 進捗パネルを畳むのは、そのパネル自身の `setState` である。この画面の
      // `build` は走らないので post-frame 判定の契機にならず、指が触れて
      // いないので `ScrollNotification` も飛ばない。それでも Inspector の
      // ビューポートは広がり、`maxScrollExtent` は変わる。**測り直す契機を
      // 持たない変化**がここにあった（レビュー3回目 P2）。
      await pumpAt(
        tester,
        // Raised from 1200 with Issue #122, which put 「AIが見た画像」 at the
        // top of the 判断材料. The window has to grow by what that row adds,
        // or folding the band away no longer brings the last row on screen
        // and the second assertion below stops being about the trigger.
        // Measured on this fixture: 1290 fails the second assertion, 1600
        // fails the premise, and 1350/1400/1450 all pass. 1400 is picked to
        // sit inside that window rather than on either edge.
        const Size(700, 1400),
        reviewableQuestion(
          // Two criteria: enough that a 判断材料 row is below the fold while
          // the band is open, few enough that folding the band away brings
          // all of them on screen. Either side of that and the test asserts
          // nothing.
          criterionCount: 2,
          rationale: '',
          comment: '',
          // A finished job whose grade is newer than it, so this question is
          // *settled*: polling stops. That matters -- a running poll rebuilds
          // this screen every three seconds and would paper over a missing
          // trigger by re-measuring on its own.
          jobs: [_jobFor('q-1')],
          gradeCreatedAt: DateTime.utc(2026, 1, 2),
        ),
      );
      expect(
        find.byKey(const Key('review-unread-material-notice')),
        findsOneWidget,
        reason: 'the premise: the material does not fit while the band is open',
      );

      await tester.tap(find.byKey(const Key('dag-toggle-button')));
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('review-unread-material-notice')),
        findsNothing,
        reason: 'every 判断材料 row is on screen now',
      );
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNotNull,
        reason: 'the whole of it is on screen, so it has been shown',
      );
    });

    testWidgets('画面の上の方が別の行に差し替わったら、末尾にいても未読に戻る', (tester) async {
      // レビュー4回目 P2-1。**逆向きの誤爆**で、こちらの方が重い。1〜3回目は
      // 「見たのに未読」だったが、これは「**見ていないのに既読**」である。
      //
      // 末尾まで読んで止まっているところへ、ポーリングが**画面より上**の行を
      // 差し替える。材料は変わったのに `extentAfter` は 0 のままなので、
      // 「末尾にいる」を新しい材料の既読の証拠に流用すると、見たことのない
      // 行に対して承認が有効になる。
      var replaced = false;
      final dependencies = AppDependencies(
        getSubmission: (_) async => _submission(),
        listQuestions: (_) async => [_question()],
        getSourcePdf: (_) async => _pocA4PortraitPdf(),
        listJobs: (_) async => [_jobFor('q-1')],
        listRecognitions: (_, _) async => [
          if (!replaced)
            _recognition(text: '（デモ）はじめに読み取った文字列です。')
          else
            // 別 ID で、**前より長い**。長いのが要点である: 末尾にいる読み手の
            // 上でこの行が伸びると、行の**下端だけが画面に入ってくる**
            // (実測で top=-113 / bottom=56、ビューポート高 214)。下端が見えた
            // ことだけを既読の根拠にすると、一言も表示されていない行が既読に
            // なる。
            _recognition(
              id: 'rec-replaced',
              text: '（デモ）あとで読み直した文字列です。' * 6,
              createdAt: DateTime.utc(2026, 1, 2),
            ),
        ],
        listGrades: (_, _) async => [
          _grade(
            rationale: '（デモ）採点根拠の文がここに入ります。' * 6,
            createdAt: DateTime.utc(2026, 1, 3),
          ),
        ],
        listAnnotations: (_, _) async => const [],
        listReviews: (_, _) async => const [],
      );

      await pumpAt(tester, desktopNarrow, dependencies);
      await _revealMaterial(tester);
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNotNull,
        reason: 'the premise: read to the end, at the end, gate open',
      );

      replaced = true;
      await tester.tap(find.byKey(const Key('review-refresh-button')));
      await tester.pumpAndSettle();
      await _settlePdf(tester);

      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNull,
        reason: '差し替わった認識文字は画面の上にあり、まだ見られていない',
      );
      expect(
        find.byKey(const Key('review-unread-material-notice')),
        findsOneWidget,
      );

      // 未読は**上**にあるので、案内もそう言うこと。
      expect(find.textContaining('この上にまだ'), findsOneWidget);

      // そして、画面が差し出す復帰操作そのもので戻れること。「続きを表示」が
      // 常に下へ動く実装だと、末尾にいるここでは移動先が現在位置と同じになり、
      // 何度押しても無反応のまま抜けられない（レビュー5回目 P2）。手でドラッグ
      // して確かめると、その壊れ方を見逃す。
      await _revealMaterial(tester);
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNotNull,
        reason: '差し替わった行を見たあとは承認できる',
      );
    });

    testWidgets('修正コメントを3行打っても、低い画面で判断材料が潰れない', (tester) async {
      // レビュー4回目 P2-2。メモ欄は1行から3行まで伸びる**可変高**である。
      // 固定高だと決めつけて下限を置いていたので、3行入力すると桁あふれし、
      // 判断材料の領域が高さ0になって「続きを表示」にも届かなくなっていた
      // ---- 承認ゲートを原理的に満たせない状態である。
      await pumpAt(
        tester,
        const Size(700, 400),
        reviewableQuestion(criterionCount: 4),
      );

      await tester.enterText(
        find.byKey(const Key('review-note-field')),
        '1行目\n2行目\n3行目',
      );
      await tester.pump();
      await _settlePdf(tester);

      expect(tester.takeException(), isNull);
      // 判断材料が読める高さで残っていること。ここが 0 になると、
      // ゲートを満たす手段が画面から消える。
      final inspector = tester.getRect(
        find.byKey(const Key('review-inspector')),
      );
      expect(inspector.height, greaterThan(0));
      expect(
        find.byKey(const Key('review-note-field')),
        findsOneWidget,
        reason: 'the note itself must not be dropped either',
      );
    });

    testWidgets('末尾へ飛ばしても、通っていない範囲が残っていれば既読にならない', (tester) async {
      // レビュー5回目 P1。ビューポートより高い行 -- 根拠本文がまさにそれで、
      // いちばん読ませたいもの -- を、上端を見たあと一気に末尾へ飛ばす。
      // 「上端と下端の両方が画面に入ったか」で判定すると、あいだが空白のまま
      // 既読になる。スクロールバーを掴んで末尾へ落としても同じことが起きる。
      await pumpAt(
        tester,
        desktopStandard,
        reviewableQuestion(rationale: '（デモ）採点根拠の文がここに入ります。' * 60),
      );
      final position = tester
          .state<ScrollableState>(
            find
                .descendant(
                  of: find.byKey(const Key('review-inspector')),
                  matching: find.byType(Scrollable),
                )
                .first,
          )
          .position;
      expect(
        position.maxScrollExtent,
        greaterThan(0),
        reason: 'the premise: the 根拠 is taller than the panel',
      );

      position.jumpTo(position.maxScrollExtent);
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNull,
        reason: '飛ばしたぶんの本文は一度も表示されていない',
      );
      expect(
        find.byKey(const Key('review-unread-material-notice')),
        findsOneWidget,
      );

      // 送って読めば、ちゃんと開く。
      await _revealMaterial(tester);
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNotNull,
      );
    });

    testWidgets('材料そのものが増えたときは未読に戻る', (tester) async {
      // The other half of the property above: a gate that never re-closes
      // would pass every "layout did not un-see it" assertion while being
      // useless. Here the *rows* change -- a newer OCR reading lands -- and
      // that is material nobody has been shown.
      var corrected = false;
      final dependencies = AppDependencies(
        getSubmission: (_) async => _submission(),
        listQuestions: (_) async => [_question()],
        getSourcePdf: (_) async => _pocA4PortraitPdf(),
        listRecognitions: (_, _) async => [
          _recognition(text: '（デモ）読み取った文字列がここに入ります。'),
          if (corrected)
            _recognition(
              id: 'rec-corrected',
              text: '（デモ）あとから届いた、より長い認識結果がここに入ります。' * 3,
              createdAt: DateTime.utc(2026, 1, 2),
            ),
        ],
        listGrades: (_, _) async => [_grade()],
        listAnnotations: (_, _) async => const [],
        listReviews: (_, _) async => const [],
      );

      await pumpAt(tester, desktopNarrow, dependencies);
      await _revealMaterial(tester);
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNotNull,
        reason: 'the premise: read to the end before anything changed',
      );

      corrected = true;
      await tester.tap(find.byKey(const Key('review-refresh-button')));
      await tester.pump();
      await _settlePdf(tester);

      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNull,
        reason: 'a row the reviewer has never seen is now on the panel',
      );
      expect(
        find.byKey(const Key('review-unread-material-notice')),
        findsOneWidget,
      );
    });

    testWidgets('末尾まで表示すれば承認できるようになる', (tester) async {
      await pumpAt(
        tester,
        desktopStandard,
        reviewableQuestion(criterionCount: 24),
      );

      // 「続きを表示」 advances one screenful per press, so that every row it
      // claims to have shown really did appear. Press it until there is
      // nothing left to show.
      for (var page = 0; page < 40; page++) {
        final button = find.byKey(const Key('review-reveal-material-button'));
        if (button.evaluate().isEmpty) break;
        await tester.tap(button);
        await tester.pumpAndSettle();
      }

      expect(
        find.byKey(const Key('review-unread-material-notice')),
        findsNothing,
      );
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNotNull,
      );

      // ...and scrolling back up to re-read something does not un-see it.
      await tester.drag(
        find.byKey(const Key('review-inspector')),
        const Offset(0, 400),
      );
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('review-approve-button')),
            )
            .onPressed,
        isNotNull,
      );
    });
  });

  group('AI採点が失敗した設問 (Issue #118)', () {
    testWidgets('失敗したことと、そこからの進み方が画面に出る', (tester) async {
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        jobs: [
          _jobFor(
            'q-1',
            state: 'failed',
            usable: false,
            lastError: 'gemini AI provider returned a malformed response',
          ),
        ],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      expect(find.byKey(const Key('review-ai-grading-failed')), findsOneWidget);
      // The queue's own diagnosis reaches the person looking at the screen:
      // it is built from a provider id, an exception class and an HTTP
      // status only (Issue #97 review round 4), never from a message that
      // could carry answer text.
      final message = tester.widget<Text>(
        find.byKey(const Key('review-ai-grading-failed-message')),
      );
      expect(message.data, contains('AIはこの設問を採点できませんでした'));
      expect(message.data, contains('malformed response'));
      // 「まだAI結果がありません」 -- the old, silent empty state -- must not
      // be what a failed question shows. That message is why the answer
      // sheet looked merely unfinished rather than stuck.
      expect(find.byKey(const Key('review-question-empty')), findsNothing);
    });

    testWidgets('切り出しが解答でなかったときは、回答欄を直せと言う (Issue #136)', (tester) async {
      // The failure this Issue is about does not end at "the AI could not
      // grade this". The crop handed to the grader was not this question's
      // answer, so the two ways out the generic notice offers are both
      // wrong: 再判定 sends the same crop to the same model, and a
      // hand-typed score would be a number for an answer nobody has seen.
      // What has to be fixed is the 回答欄 the crop came from.
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        jobs: [
          _jobFor(
            'q-1',
            state: 'failed',
            usable: false,
            lastError:
                'gemini AI provider reported that the answer image is not '
                "this question's answer (crop_not_the_answer)",
          ),
        ],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      // The question is on screen and in the failed state at all -- said
      // before the negative assertion below, so that assertion cannot pass
      // by the notice never having been built.
      expect(find.byKey(const Key('review-ai-grading-failed')), findsOneWidget);
      final message = tester.widget<Text>(
        find.byKey(const Key('review-ai-grading-failed-message')),
      );
      expect(message.data, contains('回答欄'));
      expect(message.data, contains('解答ではない'));
      expect(
        message.data,
        isNot(contains('「再判定」でもう一度AIに任せるか')),
        reason: '同じ切り出しを同じモデルへ送り直しても同じ答えが返る',
      );
    });

    testWidgets('点数を入力すると source=human の採点として保存される', (tester) async {
      final calls = <Map<String, Object?>>[];
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(
          rubric: [
            RubricCriterionResponse(
              (b) => b
                ..id = 'c-1'
                ..description = '反応の名称に言及している'
                ..maxPoints = 3
                ..position = 0,
            ),
          ],
        ),
        jobs: [_jobFor('q-1', state: 'failed', usable: false)],
        gradeManually:
            (
              submissionId,
              questionId, {
              required expectedVersion,
              required scoreAwarded,
              required scoreMaximum,
              confidence = 1.0,
              criteria = const [],
              rationale,
              comment,
              recognizedText,
              annotations,
              note,
            }) async {
              calls.add({
                'questionId': questionId,
                'expectedVersion': expectedVersion,
                'scoreAwarded': scoreAwarded,
                'scoreMaximum': scoreMaximum,
                'comment': comment,
                'criteria': {
                  for (final c in criteria) c.criterionId: c.outcome,
                },
              });
              return _reviewAction(
                _review(
                  action: 'modified',
                  version: expectedVersion + 1,
                  aiGradeResultId: null,
                  humanGradeResultId: 'grade-manual',
                ),
                submissionState: 'reviewed',
              );
            },
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      await tester.tap(find.byKey(const Key('review-manual-grade-button')));
      await tester.pumpAndSettle();
      await tester.enterText(
        find.byKey(const Key('manual-grade-dialog-score')),
        '3',
      );
      await tester.enterText(
        find.byKey(const Key('manual-grade-dialog-comment')),
        '人が採点しました',
      );
      await tester.tap(
        find.byKey(const Key('manual-grade-dialog-criterion-c-1')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('合格').last);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('manual-grade-dialog-save')));
      await tester.pumpAndSettle();

      expect(calls, hasLength(1));
      expect(calls.single['questionId'], 'q-1');
      expect(calls.single['expectedVersion'], 0);
      expect(calls.single['scoreAwarded'], 3);
      // Scored out of the question's own registered points, never a value
      // the dialog invented.
      expect(calls.single['scoreMaximum'], 5);
      expect(calls.single['comment'], '人が採点しました');
      expect(calls.single['criteria'], {'c-1': 'pass'});
    });

    testWidgets('点数を入力した設問は承認済みとして数えられる', (tester) async {
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        jobs: [_jobFor('q-1', state: 'failed', usable: false)],
        reviews: [
          _review(
            action: 'modified',
            aiGradeResultId: null,
            humanGradeResultId: 'grade-manual',
            // Recorded after the job that failed -- which is what makes it a
            // decision *about* that failure rather than about an older
            // attempt (`deriveQuestionStatus`).
            createdAt: DateTime.utc(2026, 1, 2),
          ),
        ],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      // Issue #112's own vocabulary: the rail/DAG/inspector all read
      // `deriveQuestionStatus`, and a `modified` row with no AI grade behind
      // it is still a person having decided -- otherwise the one question AI
      // could not read would hold the whole answer sheet open forever.
      expect(find.text('承認済み'), findsWidgets);
      // Already decided, so the manual-grade route is no longer offered:
      // 修正 is how a recorded decision changes.
      expect(find.byKey(const Key('review-manual-grade-button')), findsNothing);
    });

    testWidgets('AI採点がある設問には点数入力を出さない', (tester) async {
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        grades: [_grade()],
        jobs: [_jobFor('q-1')],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      expect(find.byKey(const Key('review-ai-grading-failed')), findsNothing);
      expect(find.byKey(const Key('review-manual-grade-button')), findsNothing);
    });

    testWidgets('AI採点がまだ走っている間は点数入力を出さない', (tester) async {
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        jobs: [_jobFor('q-1', state: 'running', usable: null)],
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      // A grade may still be on its way; offering to grade it by hand here
      // would invite a person to race the pipeline.
      expect(find.byKey(const Key('review-ai-grading-failed')), findsNothing);
      expect(find.byKey(const Key('review-manual-grade-button')), findsNothing);
    });

    testWidgets('再判定もそのまま選べる', (tester) async {
      final regrades = <String>[];
      final dependencies = _dependencies(
        pdfBytes: _pocA4PortraitPdf(),
        q1: _question(),
        jobs: [_jobFor('q-1', state: 'failed', usable: false)],
        regradeReview:
            (
              submissionId,
              questionId, {
              required expectedVersion,
              reason,
            }) async {
              regrades.add(questionId);
              return _reviewAction(
                _review(
                  action: 'regrade_requested',
                  version: expectedVersion + 1,
                  aiGradeResultId: null,
                  regradeJobId: 'job-regrade',
                ),
                jobId: 'job-regrade',
              );
            },
      );

      await _pumpReview(tester, dependencies);
      await tester.pump();
      await _settlePdf(tester);

      // Issue #118 受入4: a transient provider failure only needs another
      // try, and that must stay one press away rather than being replaced by
      // the manual route.
      await tester.tap(find.byKey(const Key('review-regrade-button')));
      await tester.pumpAndSettle();

      expect(regrades, ['q-1']);
    });
  });

  group('Issue #113: 答案をまたいで続けてさばく', () {
    List<SubmissionResponse> queueOf(List<String> ids) => [
      for (var i = 0; i < ids.length; i++)
        _submission(
          id: ids[i],
          state: 'ai_processed',
          studentLabel: 'answer-${ids[i]}',
        ),
    ];

    /// 判断材料を最後まで表示してから承認する。
    ///
    /// Issue #85 のゲートがあるので、**スクロールせずに承認はできない** --
    /// 押しても「この下にまだ判断材料があります」と言われるだけである。
    /// #122 で切り出し画像が先頭に入り、材料はさらに縦に伸びた。
    Future<void> approveAfterReadingMaterial(WidgetTester tester) async {
      for (var page = 0; page < 40; page++) {
        final reveal = find.byKey(const Key('review-reveal-material-button'));
        if (reveal.evaluate().isEmpty) break;
        await tester.tap(reveal);
        await tester.pumpAndSettle();
      }
      await tester.tap(find.byKey(const Key('review-approve-button')));
      await tester.pump();
      await _settlePdf(tester);
    }

    testWidgets('最後の設問を確定すると、次の答案へ進む', (tester) async {
      // **この Issue の受入条件2そのもの。** これまでは「最後の設問です」と
      // 出て止まり、ホームへ戻るしかなかった。40枚だとその往復だけで80回の
      // 操作になる。
      //
      // 設問は1問だけなので、最初の設問がそのまま最後の設問である。
      await _pumpReview(
        tester,
        _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          grades: [_grade()],
          queueSubmissions: queueOf(['sub-1', 'sub-2']),
        ),
      );
      await tester.pump();
      await _settlePdf(tester);

      await approveAfterReadingMaterial(tester);
      await tester.pump(const Duration(seconds: 1));

      expect(
        find.byKey(const ValueKey('pdf-review/test-1/sub-2')),
        findsOneWidget,
      );
      // 行き止まりの文言は、もう出さない。
      expect(find.textContaining('最後の設問です'), findsNothing);
    });

    testWidgets('次の答案が無ければ、終わったと言ってキューへ戻せる', (tester) async {
      // 「最後の設問です」で止めるのと、「すべて確認しました」と言うのとでは、
      // 講師にとって全く違う話である。
      await _pumpReview(
        tester,
        _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          grades: [_grade()],
          queueSubmissions: queueOf(['sub-1']),
        ),
      );
      await tester.pump();
      await _settlePdf(tester);

      await approveAfterReadingMaterial(tester);

      expect(find.textContaining('このテストの答案はすべて確認しました'), findsOneWidget);
      expect(find.text('答案キューへ'), findsOneWidget);
    });

    testWidgets('「答案キューへ」で移ったキューからも、戻る導線が残る (Issue #160)', (tester) async {
      // **ここが行き止まりだった。** このスナックバーは `context.go` で
      // 移っており、`go` は積んであるスタックを丸ごと捨てる。着いた答案キューに
      // アプリバーの戻る矢印が無く、Escape も Alt+Left も効かず、実機再検証 #5
      // では**アプリを再起動するまでホームへ戻れなかった**。
      //
      // 同じ画面へ入る他の2つの入口 (ホームのテストカード、テスト一覧) は
      // `push` で入るので戻れる。**入口によって戻れたり戻れなかったりしては
      // ならない** -- 利用者は自分がどう来たかを覚えていないといけなくなる。
      // 残る2つの入口は `submission_queue_page_test.dart` で見ている。
      await _pumpReview(
        tester,
        _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          grades: [_grade()],
          queueSubmissions: queueOf(['sub-1']),
          getTest: (testId) async => TestResponse(
            (b) => b
              ..id = testId
              ..name = '物理 第1回'
              ..status = 'ready'
              ..createdAt = DateTime.utc(2026, 1, 1),
          ),
        ),
      );
      await tester.pump();
      await _settlePdf(tester);

      await approveAfterReadingMaterial(tester);

      // 押す対象が本当に出ていること。これを言わずに進むと、スナックバーが
      // 出ていなくても後続が通ってしまう。
      expect(find.text('答案キューへ'), findsOneWidget);

      await tester.tap(find.text('答案キューへ'));
      await tester.pumpAndSettle();

      // 着いた先が答案キューであること (肯定形) を先に言ってから、そこに
      // 戻る導線があることを見る。
      expect(find.byType(SubmissionQueuePage), findsOneWidget);
      expect(find.byKey(const Key('queue-row-sub-1')), findsOneWidget);
      expect(find.byType(BackButton), findsOneWidget);

      await tester.tap(find.byType(BackButton));
      await tester.pumpAndSettle();

      // 戻れた先は、来た画面そのもの。
      expect(find.byType(PdfReviewPage), findsOneWidget);
    });

    testWidgets('AppBarに何枚目かが出る', (tester) async {
      // 40枚を流す作業で「あと何枚か」が見えないのは、終わりの見えない作業を
      // させることになる (受入5)。
      await _pumpReview(
        tester,
        _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          queueSubmissions: queueOf(['sub-0', 'sub-1', 'sub-2']),
        ),
      );
      await tester.pump();
      await _settlePdf(tester);

      expect(find.textContaining('2 / 3 件目'), findsOneWidget);
    });

    testWidgets('キューが引けなければ、何枚目かを書かない', (tester) async {
      // 「1 / 1」と出すと残り1枚だと読まれる。分からないことを、分かっている
      // ように見せない。
      await _pumpReview(
        tester,
        _dependencies(pdfBytes: _pocA4PortraitPdf(), q1: _question()),
      );
      await tester.pump();
      await _settlePdf(tester);

      // **先に「画面が描けている」ことを言う。** これが無いと、画面が出て
      // いなくても `findsNothing` は通ってしまい、何も検査していないテストが
      // 緑のまま残る (Issue #129 が5箇所で見つけた形)。
      expect(find.textContaining('添削レビュー'), findsOneWidget);
      expect(find.textContaining('件目'), findsNothing);
    });

    testWidgets('後回しを押すと、確定せずに次の答案へ移る', (tester) async {
      // AI採点が失敗した設問があるとその答案はいまは確定できない (Issue #118)。
      // 40枚を続けてさばく最中にそこで止まらないための逃げ道である。
      var approveCalls = 0;
      await _pumpReview(
        tester,
        _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          queueSubmissions: queueOf(['sub-1', 'sub-2']),
          approveReview:
              (
                submissionId,
                questionId, {
                required expectedVersion,
                expectedAiGradeId,
                note,
              }) async {
                approveCalls++;
                return _reviewAction(
                  _review(questionId: questionId, action: 'approved'),
                );
              },
        ),
      );
      await tester.pump();
      await _settlePdf(tester);

      await tester.tap(find.byKey(const Key('review-defer-button')));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      // 次の答案が開いている。
      expect(
        find.byKey(const ValueKey('pdf-review/test-1/sub-2')),
        findsOneWidget,
      );
      // **何も確定していない。** 答案の状態も書き換えていないので、キューに残る。
      expect(approveCalls, 0);
    });

    testWidgets('後回しは、押したことを画面で言う', (tester) async {
      // 黙って次へ飛ぶと「消えた」と読まれる。
      await _pumpReview(
        tester,
        _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          queueSubmissions: queueOf(['sub-1', 'sub-2']),
        ),
      );
      await tester.pump();
      await _settlePdf(tester);

      await tester.tap(find.byKey(const Key('review-defer-button')));
      await tester.pump();

      expect(find.textContaining('後回しにしました'), findsOneWidget);
    });

    testWidgets('S キーでも後回しになる', (tester) async {
      await _pumpReview(
        tester,
        _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          queueSubmissions: queueOf(['sub-1', 'sub-2']),
        ),
      );
      await tester.pump();
      await _settlePdf(tester);

      await tester.sendKeyEvent(LogicalKeyboardKey.keyS);
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));

      expect(
        find.byKey(const ValueKey('pdf-review/test-1/sub-2')),
        findsOneWidget,
      );
    });

    testWidgets('ほかに答案が無ければ、後回しにできないと言う', (tester) async {
      await _pumpReview(
        tester,
        _dependencies(
          pdfBytes: _pocA4PortraitPdf(),
          q1: _question(),
          queueSubmissions: queueOf(['sub-1']),
        ),
      );
      await tester.pump();
      await _settlePdf(tester);

      await tester.tap(find.byKey(const Key('review-defer-button')));
      await tester.pump();

      expect(find.textContaining('ほかに確認できる答案がありません'), findsOneWidget);
      // 行き先が無いので、この答案のままである。
      expect(
        find.byKey(const ValueKey('pdf-review/test-1/sub-1')),
        findsOneWidget,
      );
    });
  });
}
