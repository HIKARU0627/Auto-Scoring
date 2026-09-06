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
}
