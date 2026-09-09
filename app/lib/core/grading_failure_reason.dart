/// Reading the one machine-readable reason the sidecar puts in a grading
/// `Job.last_error` (Issue #136).
///
/// `last_error` is otherwise a free-text diagnosis assembled from literals
/// and numbers (provider name, exception class, HTTP status -- Issue #97
/// review round 4), and the review screen prints it as-is. One case has to
/// be more than diagnosis: when the grading AI itself reports that the image
/// it was given is not this question's answer, the reviewer's next move is
/// **not** the one the generic notice offers. Re-running the AI sends the
/// same crop to the same model, and typing a score by hand puts a number on
/// an answer nobody has seen. The fix is the 回答欄 the crop came from.
///
/// So the sidecar's own reason word travels inside that message, and this
/// reads it. The alternative -- adding the crop's status to a response
/// schema -- would mean regenerating the API client to carry a string the
/// screen already receives.
///
/// Parsed here, in `core`, for the same reason `submission_review_reason.dart`
/// is: it is a wire format, it has to be read the same way everywhere, and a
/// screen is the one place a format like this cannot be unit tested cheaply.
library;

/// The reason word the sidecar writes for a crop its own grading AI reported
/// is not this question's answer.
///
/// Kept as a constant next to the matcher so the two cannot drift: this
/// string is `domain.submission_intake.NOT_THE_ANSWER_CROP_REASON`, which is
/// also the `AnswerImage.reason` recorded on the crop itself.
const String notTheAnswerCropReason = 'crop_not_the_answer';

/// Whether [lastError] is the sidecar reporting that the graded image was
/// not this question's answer.
///
/// Substring, not equality: the message around the reason word is a
/// diagnosis meant for a person (it names the provider that answered), and
/// this must keep working when that prose changes. `null`, an empty string,
/// and any other failure return `false` -- an unrecognized message means a
/// newer sidecar is reporting something this build does not know about, and
/// the generic notice is the honest thing to show for it.
bool isNotTheAnswerCrop(String? lastError) =>
    lastError != null && lastError.contains(notTheAnswerCropReason);
