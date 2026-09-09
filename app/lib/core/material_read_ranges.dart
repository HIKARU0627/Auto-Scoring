// Which parts of a row of 判断材料 a reviewer has actually had on screen.
//
// Extracted from `features/pdf_review/pdf_review_page.dart` when a defect in
// the merge below turned out to be unreachable by the widget tests that
// covered the approval gate (Issue #85, review rounds 1-5). The gate decides
// whether 承認 may be pressed at all, so the arithmetic behind it is worth a
// test of its own rather than only being exercised through a scroll.

/// How close two range edges may be before they count as touching.
///
/// Ranges are normalised to the row's own height (`0.0`-`1.0`), so this is a
/// fraction of a row, not pixels: the same tolerance holds however the row
/// reflows (Issue #85 round 2: height is a function of width).
const double materialCoverEpsilon = 0.001;

/// [ranges] with `(start, end)` merged in, kept sorted and non-overlapping.
///
/// [ranges] must already be sorted and non-overlapping -- it is this
/// function's own previous output.
///
/// Once the new range has been placed, every remaining range is beyond it and
/// is appended unchanged. The earlier version signalled "already placed" by
/// setting the running lower bound to `double.nan`, which does not work: every
/// comparison against NaN is false, so a later range fell through to the merge
/// branch, `min(NaN, x)` kept it NaN, and a `(NaN, upper)` pair reached the
/// output. Nothing then compares equal to it -- NaN != NaN -- so the caller's
/// "did the ranges change?" check answered *yes* on every frame and rebuilt
/// forever. A bool says the same thing and cannot poison the arithmetic.
List<(double, double)> mergeMaterialRange(
  List<(double, double)> ranges,
  double start,
  double end,
) {
  final merged = <(double, double)>[];
  var lower = start;
  var upper = end;
  var placed = false;
  for (final range in ranges) {
    if (placed) {
      merged.add(range);
    } else if (range.$2 < lower - materialCoverEpsilon) {
      merged.add(range);
    } else if (range.$1 > upper + materialCoverEpsilon) {
      // This range starts after the new one ends, and the input is sorted, so
      // the new range's final extent is known: place it, then copy the rest.
      merged.add((lower, upper));
      placed = true;
      merged.add(range);
    } else {
      lower = lower < range.$1 ? lower : range.$1;
      upper = upper > range.$2 ? upper : range.$2;
    }
  }
  if (!placed) merged.add((lower, upper));
  merged.sort((a, b) => a.$1.compareTo(b.$1));
  return merged;
}

/// Whether [a] and [b] describe the same covered parts of a row.
bool sameMaterialRanges(List<(double, double)> a, List<(double, double)> b) {
  if (a.length != b.length) return false;
  for (var i = 0; i < a.length; i++) {
    if (a[i].$1 != b[i].$1 || a[i].$2 != b[i].$2) return false;
  }
  return true;
}

/// Whether [ranges] covers the row from top to bottom.
bool materialRowIsCovered(List<(double, double)>? ranges) {
  if (ranges == null || ranges.length != 1) return false;
  return ranges.single.$1 <= materialCoverEpsilon &&
      ranges.single.$2 >= 1 - materialCoverEpsilon;
}
