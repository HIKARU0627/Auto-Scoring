import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_theme.dart';
import 'package:auto_scoring_app/features/pdf_review/answer_crop_view.dart';

/// 「AIが見た画像」 (Issue #122).
///
/// The thing being pinned is not the layout -- it is that the reviewer is
/// never shown a score with nothing behind it. A crop that came out blank
/// says so, a crop that failed to load says that instead of silently
/// rendering nothing, and moving between questions never leaves one
/// question's picture under another's score.
void main() {
  /// A 2x2 PNG. Small enough to inline, real enough for `Image.memory`.
  final pngBytes = Uint8List.fromList(<int>[
    0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A, //
    0x00, 0x00, 0x00, 0x0D, 0x49, 0x48, 0x44, 0x52,
    0x00, 0x00, 0x00, 0x02, 0x00, 0x00, 0x00, 0x02,
    0x08, 0x02, 0x00, 0x00, 0x00, 0xFD, 0xD4, 0x9A,
    0x73, 0x00, 0x00, 0x00, 0x12, 0x49, 0x44, 0x41,
    0x54, 0x78, 0x9C, 0x63, 0xFC, 0xCF, 0xC0, 0xF0,
    0x9F, 0x81, 0x81, 0x01, 0x00, 0x0D, 0x86, 0x02,
    0x7E, 0xDD, 0x40, 0x8B, 0x9B, 0x00, 0x00, 0x00,
    0x00, 0x49, 0x45, 0x4E, 0x44, 0xAE, 0x42, 0x60,
    0x82,
  ]);

  Future<void> pump(
    WidgetTester tester, {
    required Future<Uint8List> Function(String, String) getAnswerImage,
    String questionId = 'q-1',
    bool isNearlyBlank = false,
  }) async {
    await tester.pumpWidget(
      MaterialApp(
        // The real theme: the blank-crop notice takes its colour from
        // `AppStatusColors`, a `ThemeExtension` only `AppTheme` installs.
        theme: AppTheme.light(),
        home: Scaffold(
          body: AnswerCropView(
            submissionId: 'sub-1',
            questionId: questionId,
            getAnswerImage: getAnswerImage,
            isNearlyBlank: isNearlyBlank,
          ),
        ),
      ),
    );
  }

  testWidgets('shows the crop the AI was sent', (tester) async {
    await pump(tester, getAnswerImage: (_, _) async => pngBytes);
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('review-answer-crop-image')), findsOneWidget);
    expect(find.text('AIが見た画像'), findsOneWidget);
  });

  testWidgets('says so when the crop is as good as blank', (tester) async {
    await pump(
      tester,
      getAnswerImage: (_, _) async => pngBytes,
      isNearlyBlank: true,
    );
    await tester.pumpAndSettle();

    expect(
      find.byKey(const Key('review-answer-crop-blank-notice')),
      findsOneWidget,
    );
  });

  testWidgets('names both causes rather than asserting one', (tester) async {
    // Nothing can tell "the box is in the wrong place" from "the student
    // wrote nothing" by looking at the crop, and Issue #122 measured that a
    // threshold raised until it could would start rejecting real answers.
    await pump(
      tester,
      getAnswerImage: (_, _) async => pngBytes,
      isNearlyBlank: true,
    );
    await tester.pumpAndSettle();

    final notice = tester.widget<Text>(
      find.descendant(
        of: find.byKey(const Key('review-answer-crop-blank-notice')),
        matching: find.byType(Text),
      ),
    );
    expect(notice.data, contains('ずれている'));
    expect(notice.data, contains('無記入'));
  });

  testWidgets('a healthy crop carries no warning', (tester) async {
    await pump(tester, getAnswerImage: (_, _) async => pngBytes);
    await tester.pumpAndSettle();

    expect(
      find.byKey(const Key('review-answer-crop-blank-notice')),
      findsNothing,
    );
  });

  testWidgets('says the crop is missing rather than showing nothing', (
    tester,
  ) async {
    await pump(
      tester,
      getAnswerImage: (_, _) async => throw SidecarApiException(
        SidecarErrorKind.badResponse,
        'no answer image recorded for this question',
        statusCode: 404,
      ),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('review-answer-crop-error')), findsOneWidget);
    expect(find.byKey(const Key('review-answer-crop-image')), findsNothing);
  });

  testWidgets('a sidecar failure does not escape as an unhandled error', (
    tester,
  ) async {
    await pump(
      tester,
      getAnswerImage: (_, _) async =>
          throw SidecarApiException(SidecarErrorKind.unavailable, 'offline'),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('review-answer-crop-error')), findsOneWidget);
    expect(tester.takeException(), isNull);
  });

  testWidgets('a late response for the previous question is discarded', (
    tester,
  ) async {
    // Otherwise one question's picture ends up under another's score --
    // precisely the confusion this widget exists to prevent.
    final pending = <String, Completer<Uint8List>>{};
    Future<Uint8List> load(String submissionId, String questionId) {
      final completer = Completer<Uint8List>();
      pending[questionId] = completer;
      return completer.future;
    }

    await pump(tester, getAnswerImage: load, questionId: 'q-1');
    await pump(tester, getAnswerImage: load, questionId: 'q-2');

    pending['q-1']!.complete(pngBytes);
    // `pump`, not `pumpAndSettle`: q-2 is still loading, and its progress
    // indicator never settles.
    await tester.pump();

    // q-1's bytes arrived after the move to q-2, so nothing is painted.
    expect(find.byKey(const Key('review-answer-crop-image')), findsNothing);
    expect(find.byKey(const Key('review-answer-crop-loading')), findsOneWidget);

    pending['q-2']!.complete(pngBytes);
    await tester.pump();
    await tester.pump();
    expect(find.byKey(const Key('review-answer-crop-image')), findsOneWidget);
  });
}
