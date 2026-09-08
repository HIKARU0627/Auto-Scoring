import 'package:auto_scoring_app/core/material_read_ranges.dart';
import 'package:flutter_test/flutter_test.dart';

void main() {
  group('mergeMaterialRange', () {
    test('inserts into a gap without corrupting the ranges after it', () {
      // Issue #85 round 5 left a `double.nan` sentinel behind to mean "the new
      // range has been placed". Every comparison against NaN is false, so the
      // range after the gap fell through to the merge branch and a
      // `(NaN, ...)` pair reached the output.
      final merged = mergeMaterialRange(
        const [(0.0, 0.1), (0.4, 0.5), (0.8, 0.9)],
        0.2,
        0.3,
      );

      expect(merged, const [(0.0, 0.1), (0.2, 0.3), (0.4, 0.5), (0.8, 0.9)]);
      expect(
        merged.any((r) => r.$1.isNaN || r.$2.isNaN),
        isFalse,
        reason:
            'a NaN edge never compares equal to itself, so the caller '
            'would see the ranges change on every frame and rebuild forever',
      );
    });

    test('the result compares equal to itself, so a redraw settles', () {
      final once = mergeMaterialRange(
        const [(0.0, 0.1), (0.4, 0.5), (0.8, 0.9)],
        0.2,
        0.3,
      );
      final twice = mergeMaterialRange(
        const [(0.0, 0.1), (0.4, 0.5), (0.8, 0.9)],
        0.2,
        0.3,
      );

      expect(sameMaterialRanges(once, twice), isTrue);
    });

    test('absorbs ranges the new one overlaps or touches', () {
      expect(
        mergeMaterialRange(const [(0.0, 0.2), (0.3, 0.4)], 0.15, 0.35),
        const [(0.0, 0.4)],
      );
    });

    test('appends when the new range is past everything', () {
      expect(mergeMaterialRange(const [(0.0, 0.2)], 0.6, 0.7), const [
        (0.0, 0.2),
        (0.6, 0.7),
      ]);
    });

    test('places the new range first when it is before everything', () {
      expect(mergeMaterialRange(const [(0.6, 0.7)], 0.0, 0.2), const [
        (0.0, 0.2),
        (0.6, 0.7),
      ]);
    });

    test('a row is covered only once the ranges reach both edges', () {
      expect(materialRowIsCovered(null), isFalse);
      expect(materialRowIsCovered(const [(0.0, 0.5)]), isFalse);
      expect(
        materialRowIsCovered(const [(0.0, 0.5), (0.5, 1.0)]),
        isFalse,
        reason: 'two ranges mean a gap was never closed',
      );
      expect(materialRowIsCovered(const [(0.0, 1.0)]), isTrue);
    });
  });
}
