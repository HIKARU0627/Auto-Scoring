import 'dart:ui';

import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/pdf_review_geometry.dart';

/// The same 5 normalized test points PoC 3 (Issue #12,
/// `docs/poc-3-pdf-coordinates.md`) stamped on every fixture PDF -- picked
/// for their asymmetry so an axis swap or a missed rotation would be
/// visible. `backend/tests/test_pdf_engine_roundtrip.py::_TEST_POINTS` is the
/// source of truth; kept in sync by hand since this is a different language.
const _pocTestPoints = [
  Offset(0.12, 0.15),
  Offset(0.5, 0.5),
  Offset(0.9, 0.25),
  Offset(0.25, 0.88),
  Offset(0.82, 0.8),
];

/// PoC 3's A4-portrait fixture page size in PDF points
/// (`docs/poc-3-pdf-coordinates.md` fixture table) -- `pdfrx` reports a
/// page's rendered size in this same unit (1 CSS/PDF point == 1 logical
/// pixel at the viewer's 1.0 scale), so a page rendered at "natural" size
/// has exactly this pixel size.
const _a4PortraitPageSize = Size(595.0, 842.0);

/// The corresponding fixture rotated 90° (`a4-rotate-90.pdf`): pdfrx already
/// applies `/Rotate` when reporting a page's *displayed* width/height (PoC 3
/// "displayed = (nx·Wd, ny·Hd)" -- Wd/Hd swap for 90/270), so the same
/// normalized points map onto the swapped page size.
const _a4Rotate90PageSize = Size(842.0, 595.0);

NormalizedRectResponse _point(Offset normalized) => NormalizedRectResponse(
  (b) => b
    ..x = normalized.dx
    ..y = normalized.dy
    ..width = 0
    ..height = 0,
);

void main() {
  group('normalizedRectToLocal', () {
    for (final point in _pocTestPoints) {
      test('places (${point.dx}, ${point.dy}) at the expected pixel offset on '
          'an A4 portrait page', () {
        final rect = normalizedRectToLocal(_point(point), _a4PortraitPageSize);

        expect(rect.left, closeTo(point.dx * _a4PortraitPageSize.width, 1e-9));
        expect(rect.top, closeTo(point.dy * _a4PortraitPageSize.height, 1e-9));
      });

      test('places (${point.dx}, ${point.dy}) at the expected pixel offset on '
          'the same page rotated 90°', () {
        final rect = normalizedRectToLocal(_point(point), _a4Rotate90PageSize);

        expect(rect.left, closeTo(point.dx * _a4Rotate90PageSize.width, 1e-9));
        expect(rect.top, closeTo(point.dy * _a4Rotate90PageSize.height, 1e-9));
      });
    }

    test('scales width/height along with the page size (zoom-independent)', () {
      final rect = NormalizedRectResponse(
        (b) => b
          ..x = 0.1
          ..y = 0.2
          ..width = 0.3
          ..height = 0.4,
      );

      // pdfrx reports the *current on-screen* page size, already scaled by
      // whatever zoom the reviewer picked -- doubling it here stands in for
      // "the reviewer zoomed to 2x" and the overlay must scale with it
      // (Issue #21 acceptance: overlay stays aligned with the PDF across
      // zoom/scroll/rotation).
      final at1x = normalizedRectToLocal(rect, const Size(1000, 2000));
      final at2x = normalizedRectToLocal(rect, const Size(2000, 4000));

      expect(at2x.left, closeTo(at1x.left * 2, 1e-9));
      expect(at2x.top, closeTo(at1x.top * 2, 1e-9));
      expect(at2x.width, closeTo(at1x.width * 2, 1e-9));
      expect(at2x.height, closeTo(at1x.height * 2, 1e-9));
    });
  });

  group('resolveAnnotationRect', () {
    AnnotationResponse annotation({
      String kind = 'circle',
      NormalizedRectResponse? rect,
      String? anchorText,
    }) => AnnotationResponse(
      (b) => b
        ..id = 'anno-1'
        ..submissionId = 'sub-1'
        ..questionId = 'q-1'
        ..source_ = 'ai'
        ..kind = kind
        ..rect = rect?.toBuilder()
        ..anchorText = anchorText
        ..createdAt = DateTime.utc(2026, 1, 1),
    );

    RecognitionResponse recognitionWithBoxes(
      List<(String, NormalizedRectResponse)> boxes,
    ) => RecognitionResponse(
      (b) => b
        ..id = 'rec-1'
        ..submissionId = 'sub-1'
        ..questionId = 'q-1'
        ..source_ = 'ai'
        ..stage = 'ocr'
        ..text = 'placeholder'
        ..confidence = 0.9
        ..createdAt = DateTime.utc(2026, 1, 1)
        ..boxes.addAll([
          for (final (text, rect) in boxes)
            BoundingBoxResponse(
              (b) => b
                ..text = text
                ..x = rect.x
                ..y = rect.y
                ..width = rect.width
                ..height = rect.height,
            ),
        ]),
    );

    test('an explicit rect is used as-is', () {
      final explicitRect = NormalizedRectResponse(
        (b) => b
          ..x = 0.1
          ..y = 0.1
          ..width = 0.2
          ..height = 0.2,
      );

      final resolved = resolveAnnotationRect(
        annotation: annotation(rect: explicitRect),
        questionAnswerArea: null,
        recognitions: const [],
      );

      // Not `same()`: the annotation's `rect` getter returns whatever
      // built_value produced when building the annotation from a builder
      // seeded with `explicitRect.toBuilder()`, not necessarily the exact
      // same instance -- field equality is what actually matters here.
      expect(resolved?.x, explicitRect.x);
      expect(resolved?.y, explicitRect.y);
      expect(resolved?.width, explicitRect.width);
      expect(resolved?.height, explicitRect.height);
    });

    test('an anchor_text annotation resolves to the matching OCR word box, '
        'per simplified-design-spec §12.3, when the question has no confirmed '
        'answer_area yet (OCR ran against the full, uncropped page)', () {
      final wordBox = NormalizedRectResponse(
        (b) => b
          ..x = 0.4
          ..y = 0.5
          ..width = 0.05
          ..height = 0.03,
      );

      final resolved = resolveAnnotationRect(
        annotation: annotation(kind: 'underline', anchorText: '行く'),
        questionAnswerArea: null,
        recognitions: [
          recognitionWithBoxes([('走る', _dummyRect), ('行く', wordBox)]),
        ],
      );

      expect(resolved?.x, wordBox.x);
      expect(resolved?.y, wordBox.y);
      expect(resolved?.width, wordBox.width);
      expect(resolved?.height, wordBox.height);
    });

    test('an anchor_text annotation resolves to the matching OCR word box '
        "mapped from the cropped answer image's coordinates into page "
        'coordinates through the question\'s answer_area (P1 review: '
        'RecognitionJobProcessor persists boxes normalized against the crop '
        'the OCR provider actually saw, not the page)', () {
      // The answer area covers only the bottom-right quadrant of the
      // page -- picked to be asymmetric so a missed offset or a missed
      // scale would both be visible.
      final answerArea = NormalizedRectResponse(
        (b) => b
          ..x = 0.5
          ..y = 0.6
          ..width = 0.4
          ..height = 0.3,
      );
      // Normalized against the *crop*: dead center of the answer image.
      final cropRelativeBox = NormalizedRectResponse(
        (b) => b
          ..x = 0.5
          ..y = 0.5
          ..width = 0.1
          ..height = 0.1,
      );

      final resolved = resolveAnnotationRect(
        annotation: annotation(kind: 'underline', anchorText: '酸素'),
        questionAnswerArea: answerArea,
        recognitions: [
          recognitionWithBoxes([('酸素', cropRelativeBox)]),
        ],
      );

      // page.x = area.x + box.x * area.width = 0.5 + 0.5*0.4 = 0.7
      expect(resolved?.x, closeTo(0.7, 1e-9));
      // page.y = area.y + box.y * area.height = 0.6 + 0.5*0.3 = 0.75
      expect(resolved?.y, closeTo(0.75, 1e-9));
      // page.width = box.width * area.width = 0.1 * 0.4 = 0.04
      expect(resolved?.width, closeTo(0.04, 1e-9));
      // page.height = box.height * area.height = 0.1 * 0.3 = 0.03
      expect(resolved?.height, closeTo(0.03, 1e-9));
    });

    for (final degenerateArea in [
      (
        'zero width',
        NormalizedRectResponse(
          (b) => b
            ..x = 0.5
            ..y = 0.6
            ..width = 0
            ..height = 0.3,
        ),
      ),
      (
        'zero height',
        NormalizedRectResponse(
          (b) => b
            ..x = 0.5
            ..y = 0.6
            ..width = 0.4
            ..height = 0,
        ),
      ),
    ]) {
      test('treats a persisted answer_area with ${degenerateArea.$1} the same '
          'as no answer_area at all -- OCR ran against the full page, not a '
          'zero-size crop (P2 review: _build_answer_image falls back to the '
          'full page for this exact case, so this must not collapse the '
          "annotation's rect to zero size)", () {
        final wordBox = NormalizedRectResponse(
          (b) => b
            ..x = 0.4
            ..y = 0.5
            ..width = 0.05
            ..height = 0.03,
        );

        final resolved = resolveAnnotationRect(
          annotation: annotation(kind: 'underline', anchorText: '酸素'),
          questionAnswerArea: degenerateArea.$2,
          recognitions: [
            recognitionWithBoxes([('酸素', wordBox)]),
          ],
        );

        expect(resolved?.x, wordBox.x);
        expect(resolved?.y, wordBox.y);
        expect(resolved?.width, wordBox.width);
        expect(resolved?.height, wordBox.height);
      });
    }

    test('a box still matches despite the line break the OCR leaves on its '
        'text -- Document AI slices a token out of the page text, so the '
        'detected break travels with it (Issue #141)', () {
      final wordBox = NormalizedRectResponse(
        (b) => b
          ..x = 0.1
          ..y = 0.2
          ..width = 0.3
          ..height = 0.1,
      );

      final resolved = resolveAnnotationRect(
        annotation: annotation(kind: 'cross', anchorText: '酸素'),
        questionAnswerArea: null,
        recognitions: [
          recognitionWithBoxes([('酸素\n', wordBox)]),
        ],
      );

      expect(resolved?.x, wordBox.x);
      expect(resolved?.y, wordBox.y);
      expect(resolved?.width, wordBox.width);
      expect(resolved?.height, wordBox.height);
    });

    test('an anchor spanning several boxes resolves to their union -- an OCR '
        'box is one token, so 葉緑体で arrives as 葉緑体 + で', () {
      final resolved = resolveAnnotationRect(
        annotation: annotation(kind: 'cross', anchorText: '葉緑体で'),
        questionAnswerArea: null,
        recognitions: [
          recognitionWithBoxes([
            (
              '葉緑体',
              NormalizedRectResponse(
                (b) => b
                  ..x = 0.10
                  ..y = 0.20
                  ..width = 0.08
                  ..height = 0.04,
              ),
            ),
            (
              'で',
              NormalizedRectResponse(
                (b) => b
                  ..x = 0.18
                  ..y = 0.21
                  ..width = 0.04
                  ..height = 0.03,
              ),
            ),
          ]),
        ],
      );

      expect(resolved?.x, closeTo(0.10, 1e-9));
      expect(resolved?.y, closeTo(0.20, 1e-9));
      expect(resolved?.width, closeTo(0.12, 1e-9));
      expect(resolved?.height, closeTo(0.04, 1e-9));
    });

    test('a full-width anchor matches the ASCII the OCR read', () {
      final wordBox = NormalizedRectResponse(
        (b) => b
          ..x = 0.4
          ..y = 0.1
          ..width = 0.05
          ..height = 0.03,
      );

      final resolved = resolveAnnotationRect(
        annotation: annotation(kind: 'circle', anchorText: '\uFF41'),
        questionAnswerArea: null,
        recognitions: [
          recognitionWithBoxes([('a\n', wordBox)]),
        ],
      );

      expect(resolved?.x, wordBox.x);
      expect(resolved?.width, wordBox.width);
    });

    test('the shortest run containing the anchor wins -- the tightest rect is '
        'the one about the words the mark is for', () {
      final tight = NormalizedRectResponse(
        (b) => b
          ..x = 0.50
          ..y = 0.20
          ..width = 0.04
          ..height = 0.03,
      );

      final resolved = resolveAnnotationRect(
        annotation: annotation(kind: 'cross', anchorText: '酸素'),
        questionAnswerArea: null,
        recognitions: [
          recognitionWithBoxes([
            (
              '酸',
              NormalizedRectResponse(
                (b) => b
                  ..x = 0.10
                  ..y = 0.20
                  ..width = 0.02
                  ..height = 0.03,
              ),
            ),
            (
              '素',
              NormalizedRectResponse(
                (b) => b
                  ..x = 0.12
                  ..y = 0.20
                  ..width = 0.02
                  ..height = 0.03,
              ),
            ),
            ('酸素', tight),
          ]),
        ],
      );

      expect(resolved?.x, tight.x);
      expect(resolved?.width, tight.width);
    });

    test('a run that reads far more than the anchor is refused -- the rect '
        'drawn is the run\'s, not the anchor\'s', () {
      final resolved = resolveAnnotationRect(
        annotation: annotation(kind: 'cross', anchorText: 'の'),
        questionAnswerArea: null,
        recognitions: [
          recognitionWithBoxes([
            (
              '光合成は葉緑体で行われる',
              NormalizedRectResponse(
                (b) => b
                  ..x = 0.1
                  ..y = 0.2
                  ..width = 0.8
                  ..height = 0.04,
              ),
            ),
          ]),
        ],
      );

      expect(resolved, isNull);
    });

    test('boxes that are not consecutive do not match -- a model joining two '
        'different sub-answers into one anchor names no run on the page', () {
      final resolved = resolveAnnotationRect(
        annotation: annotation(kind: 'cross', anchorText: '水デンプン'),
        questionAnswerArea: null,
        recognitions: [
          recognitionWithBoxes([
            (
              '水\n',
              NormalizedRectResponse(
                (b) => b
                  ..x = 0.10
                  ..y = 0.20
                  ..width = 0.04
                  ..height = 0.03,
              ),
            ),
            (
              'b\n',
              NormalizedRectResponse(
                (b) => b
                  ..x = 0.10
                  ..y = 0.30
                  ..width = 0.04
                  ..height = 0.03,
              ),
            ),
            (
              'デンプン',
              NormalizedRectResponse(
                (b) => b
                  ..x = 0.10
                  ..y = 0.40
                  ..width = 0.08
                  ..height = 0.03,
              ),
            ),
          ]),
        ],
      );

      expect(resolved, isNull);
    });

    test('no kind falls back to the score_area when its anchor matched '
        'nothing -- the position is unknown, so nothing on the answer may '
        'claim to know it (Issue #141, simplified-design-spec §12.4)', () {
      for (final kind in ['circle', 'cross', 'triangle', 'score']) {
        final resolved = resolveAnnotationRect(
          annotation: annotation(kind: kind, anchorText: '存在しない語'),
          questionAnswerArea: null,
          recognitions: [
            recognitionWithBoxes([('別の語', _dummyRect)]),
          ],
        );
        expect(resolved, isNull, reason: 'kind: $kind');
      }
    });

    test('an explicit rect still places a shape kind -- dropping the fallback '
        'must not stop a mark whose position really is known', () {
      final placed = NormalizedRectResponse(
        (b) => b
          ..x = 0.2
          ..y = 0.3
          ..width = 0.1
          ..height = 0.05,
      );

      final resolved = resolveAnnotationRect(
        annotation: annotation(kind: 'circle', rect: placed),
        questionAnswerArea: null,
        recognitions: const [],
      );

      // Field equality, not `same()` -- see the note on the first test.
      expect(resolved?.x, placed.x);
      expect(resolved?.y, placed.y);
      expect(resolved?.width, placed.width);
      expect(resolved?.height, placed.height);
    });

    test('an annotation with no rect and no OCR match is left unresolved '
        '(routed to the comment fallback area by the caller, per '
        'simplified-design-spec §12.4)', () {
      final resolved = resolveAnnotationRect(
        annotation: annotation(kind: 'comment', anchorText: '存在しない語'),
        questionAnswerArea: null,
        recognitions: const [],
      );

      expect(resolved, isNull);
    });
  });
}

final _dummyRect = NormalizedRectResponse(
  (b) => b
    ..x = 0.01
    ..y = 0.01
    ..width = 0.01
    ..height = 0.01,
);
