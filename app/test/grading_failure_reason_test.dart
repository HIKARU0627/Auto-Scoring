import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/core/grading_failure_reason.dart';

/// Reading the sidecar's reason word out of a grading `Job.last_error`
/// (Issue #136).
///
/// The word is a wire format shared with
/// `domain.submission_intake.NOT_THE_ANSWER_CROP_REASON`; these pin what the
/// app expects of it, so a change on either side breaks a test rather than
/// silently sending the reviewer back to the generic "AI could not grade
/// this" notice for the one failure that has a specific fix.
void main() {
  group('isNotTheAnswerCrop', () {
    test('recognizes the sidecar message the grading job actually writes', () {
      expect(
        isNotTheAnswerCrop(
          'gemini AI provider reported that the answer image is not this '
          "question's answer (crop_not_the_answer)",
        ),
        isTrue,
      );
    });

    test('another permanent failure is not this one', () {
      expect(
        isNotTheAnswerCrop('gemini AI provider returned a malformed response'),
        isFalse,
      );
      expect(
        isNotTheAnswerCrop('gemini AI provider grading requires a rubric'),
        isFalse,
      );
    });

    test('a crop flagged as blank is a different reason word', () {
      // The two claims are kept apart end to end (Issue #136): "this is not
      // the answer" points at the 回答欄, while "the answer is blank" may
      // well be a correct 0 on an ordinary answer sheet.
      expect(isNotTheAnswerCrop('crop_nearly_blank'), isFalse);
    });

    test('no failure, or none recorded, is not a claim', () {
      expect(isNotTheAnswerCrop(null), isFalse);
      expect(isNotTheAnswerCrop(''), isFalse);
    });
  });
}
