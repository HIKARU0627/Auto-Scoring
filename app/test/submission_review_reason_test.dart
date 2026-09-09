import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/core/submission_review_reason.dart';

/// Reading the sidecar's `review_reason` (Issue #122).
///
/// The string is a wire format shared with
/// `adapters.submission_intake._describe_flagged_images`; these pin the shape
/// the app expects of it, so a change on either side breaks a test rather
/// than silently putting a warning on the wrong question -- or on none.
void main() {
  group('questionsFlaggedAs', () {
    test('reads the ids of one reason', () {
      expect(
        questionsFlaggedAs('crop_nearly_blank:q-1,q-2', nearlyBlankCropReason),
        {'q-1', 'q-2'},
      );
    });

    test('reads one reason out of several clauses', () {
      expect(
        questionsFlaggedAs(
          'answer_area_undefined:q-1;crop_nearly_blank:q-2,q-3',
          nearlyBlankCropReason,
        ),
        {'q-2', 'q-3'},
      );
    });

    test('a different reason does not leak into this one', () {
      // The two send the reviewer to different places -- the registration
      // screen for one, the answer itself for the other.
      expect(
        questionsFlaggedAs('answer_area_undefined:q-1', nearlyBlankCropReason),
        isEmpty,
      );
    });

    test('a reason that only shares a prefix does not match', () {
      expect(
        questionsFlaggedAs('crop_nearly_blank_v2:q-1', nearlyBlankCropReason),
        isEmpty,
      );
    });

    test('null and empty are no flags, not an error', () {
      expect(questionsFlaggedAs(null, nearlyBlankCropReason), isEmpty);
      expect(questionsFlaggedAs('', nearlyBlankCropReason), isEmpty);
    });

    test('an unparseable reason flags nothing', () {
      // A newer sidecar reporting something this build does not know about.
      // Unknown is shown as nothing, never guessed at: a warning on the
      // wrong question is worse than no warning at all.
      expect(
        questionsFlaggedAs('something_new', nearlyBlankCropReason),
        isEmpty,
      );
      expect(questionsFlaggedAs(':q-1', nearlyBlankCropReason), isEmpty);
    });

    test('ignores blank ids and surrounding whitespace', () {
      expect(
        questionsFlaggedAs(
          'crop_nearly_blank: q-1 , ,q-2',
          nearlyBlankCropReason,
        ),
        {'q-1', 'q-2'},
      );
    });

    test('a coverage reason with a non-id value is not read as ids', () {
      // `missing_pages:2` and `extra_pages:3>2` share the shape but carry
      // page numbers, not question ids -- asking for a different reason must
      // simply not match them.
      expect(
        questionsFlaggedAs(
          'missing_pages:2;extra_pages:3>2',
          nearlyBlankCropReason,
        ),
        isEmpty,
      );
    });
  });

  group('hasNearlyBlankCrop', () {
    test('is true only for the questions the sidecar flagged', () {
      const reason = 'answer_area_undefined:q-1;crop_nearly_blank:q-2';

      expect(hasNearlyBlankCrop(reason, 'q-2'), isTrue);
      expect(hasNearlyBlankCrop(reason, 'q-1'), isFalse);
      expect(hasNearlyBlankCrop(reason, 'q-3'), isFalse);
      expect(hasNearlyBlankCrop(null, 'q-2'), isFalse);
    });
  });
}
