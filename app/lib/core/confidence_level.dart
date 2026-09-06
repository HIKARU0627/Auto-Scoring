/// Display-only bucketing of a 0..1 Recognition/Grading Confidence value
/// (simplified-design-spec.md §8.2/§10) into a coarse level a reviewer can
/// scan quickly.
///
/// The thresholds below are a UI categorization only -- they do not gate
/// anything (no auto-confirm, no blocking). The actual "low Confidence"
/// business threshold is an open decision
/// (`docs/data-model-and-local-storage.md` §9, `docs/business-rules-and-
/// evaluation-data.md` §3 (C)); see `docs/pdf-review-overlay.md` for why this
/// screen picks a provisional display split instead of waiting on it.
enum ConfidenceLevel {
  high,
  medium,
  low;

  static const double _mediumThreshold = 0.7;
  static const double _highThreshold = 0.9;

  static ConfidenceLevel of(double confidence) {
    if (confidence >= _highThreshold) return ConfidenceLevel.high;
    if (confidence >= _mediumThreshold) return ConfidenceLevel.medium;
    return ConfidenceLevel.low;
  }

  /// Japanese label shown alongside the icon -- confidence must never be
  /// distinguished by color alone (Issue #21 acceptance criteria).
  String get label => switch (this) {
    ConfidenceLevel.high => '高',
    ConfidenceLevel.medium => '中',
    ConfidenceLevel.low => '低',
  };
}
