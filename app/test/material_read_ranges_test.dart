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

    test('merging the same range twice changes nothing, so a redraw settles', () {
      // The defect this file exists for showed up as a redraw that never
      // stopped, not as a wrong value: the caller asks "did the ranges
      // change?" every frame, and a merge that does not converge answers
      // "yes" forever. Feeding the output back in is what states that;
      // computing the same input twice only states that the function is
      // deterministic, which every version of it was (review of PR #110).
      const cases = [
        (<(double, double)>[], 0.0, 1.0),
        ([(0.0, 0.1), (0.4, 0.5), (0.8, 0.9)], 0.2, 0.3),
        ([(0.7969, 0.9573)], 0.0764, 0.0765),
        ([(0.0, 0.2), (0.4, 0.6), (0.8, 1.0)], 0.21, 0.79),
        ([(0.2, 0.3)], 0.0, 0.1),
        ([(0.0, 0.1)], 0.9, 1.0),
      ];

      for (final (ranges, start, end) in cases) {
        final once = mergeMaterialRange(ranges, start, end);
        final twice = mergeMaterialRange(once, start, end);
        expect(
          sameMaterialRanges(once, twice),
          isTrue,
          reason:
              '$ranges + ($start, $end) does not converge -- the caller '
              'would answer "changed" on every frame and never stop rebuilding',
        );
      }
    });

    test(
      'the output is sorted, which is what lets the caller compare in order',
      () {
        final merged = mergeMaterialRange(
          const [(0.0, 0.1), (0.4, 0.5), (0.8, 0.9)],
          0.2,
          0.3,
        );

        for (var i = 1; i < merged.length; i++) {
          expect(
            merged[i - 1].$1 <= merged[i].$1,
            isTrue,
            reason:
                'sameMaterialRanges compares position by position, so an '
                'unsorted result would read as "changed" against an equal set',
          );
        }
      },
    );

    test('a rounding-sized gap still counts as touching', () {
      // What the epsilon is for. Without it these stay two ranges and the row
      // never reads as covered, so 承認 can never be pressed.
      // A literal gap, not one derived from the epsilon: deriving it means an
      // epsilon of zero closes the gap too, and the test stops discriminating
      // (found while re-running the review's mutants).
      const gap = 0.0005;
      expect(gap, lessThan(materialCoverEpsilon));
      final merged = mergeMaterialRange(const [(0.0, 0.5)], 0.5 + gap, 1.0);

      expect(merged, hasLength(1));
      expect(materialRowIsCovered(merged), isTrue);
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
        materialRowIsCovered(const [(0.5, 1.0)]),
        isFalse,
        reason:
            'the top half was never on screen -- reaching the bottom edge '
            'is not the same as having seen the row',
      );
      expect(
        materialRowIsCovered(const [(0.0, 0.5), (0.5, 1.0)]),
        isFalse,
        reason: 'two ranges mean a gap was never closed',
      );
      expect(materialRowIsCovered(const [(0.0, 1.0)]), isTrue);
    });
  });

  group('sameMaterialRanges', () {
    test('looks at both edges, not just where a range starts', () {
      expect(
        sameMaterialRanges(const [(0.0, 0.5)], const [(0.0, 0.6)]),
        isFalse,
      );
      expect(
        sameMaterialRanges(const [(0.0, 0.5)], const [(0.1, 0.5)]),
        isFalse,
      );
    });

    test('a different number of ranges is a different set', () {
      expect(
        sameMaterialRanges(const [(0.0, 0.5)], const [(0.0, 0.5), (0.7, 0.9)]),
        isFalse,
      );
      expect(
        sameMaterialRanges(const [(0.0, 0.5), (0.7, 0.9)], const [(0.0, 0.5)]),
        isFalse,
      );
      expect(sameMaterialRanges(const [], const [(0.0, 0.5)]), isFalse);
    });

    test('the same set is the same', () {
      expect(
        sameMaterialRanges(const [(0.0, 0.5)], const [(0.0, 0.5)]),
        isTrue,
      );
      expect(sameMaterialRanges(const [], const []), isTrue);
    });
  });
}
