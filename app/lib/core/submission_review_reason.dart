/// Reading `Submission.review_reason` (Issue #122).
///
/// The sidecar records *why* a submission needs a human as one short,
/// machine-readable string rather than prose, so the app can route the
/// reviewer to the right place instead of showing them a sentence
/// (`domain.submission_intake.describe_coverage_issue` and
/// `adapters.submission_intake._describe_flagged_images`). The shape is
/// `<reason>:<value>` clauses joined by `;`, and for the per-question reasons
/// the value is a comma-separated list of question ids:
///
/// ```text
/// answer_area_undefined:q-1;crop_nearly_blank:q-2,q-3
/// ```
///
/// Parsed here, in `core`, rather than inside the review screen: it is a
/// wire format, it has to be read the same way everywhere, and a screen is
/// the one place a format like this cannot be unit tested cheaply.
library;

/// The reason the sidecar records for a crop that came out as good as blank
/// -- the answer area landed on the margin, or the student wrote nothing.
///
/// Kept as a constant next to the parser so the two cannot drift: this
/// string is `domain.submission_intake.NEARLY_BLANK_CROP_REASON`.
const String nearlyBlankCropReason = 'crop_nearly_blank';

/// The question ids [reviewReason] flags with [reason].
///
/// Returns an empty set for `null`, for a reason that is not present, and
/// for anything that does not parse -- an unrecognized string means a newer
/// sidecar is reporting something this build does not know about, and
/// guessing at it would put a warning on the wrong question. Unknown is
/// shown as nothing, never as a claim.
Set<String> questionsFlaggedAs(String? reviewReason, String reason) {
  if (reviewReason == null || reviewReason.isEmpty) {
    return const <String>{};
  }
  final flagged = <String>{};
  for (final clause in reviewReason.split(';')) {
    final separator = clause.indexOf(':');
    if (separator <= 0 || clause.substring(0, separator).trim() != reason) {
      continue;
    }
    for (final id in clause.substring(separator + 1).split(',')) {
      final trimmed = id.trim();
      if (trimmed.isNotEmpty) {
        flagged.add(trimmed);
      }
    }
  }
  return flagged;
}

/// Whether [questionId]'s crop was flagged as nearly blank.
bool hasNearlyBlankCrop(String? reviewReason, String questionId) =>
    questionsFlaggedAs(
      reviewReason,
      nearlyBlankCropReason,
    ).contains(questionId);
