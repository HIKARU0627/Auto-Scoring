import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

/// tests for PagesApi
void main() {
  final instance = AutoScoringApi().getPagesApi();

  group(PagesApi, () {
    // Get Answer Layout Page Image
    //
    // One page of the test's answer sheet, rasterized by the same pdfium that performs the coordinate transform (PoC 6, approach B).  **A normalized coordinate is built from the returned image's own pixel size, and from nothing else** (`normalized_x = click_px / image_width_px`). pdfium drew the displayed page into those pixels, so that division cannot disagree with this sidecar's coordinate transform.  Do **not** divide by the `displayed_width` / `displayed_height` reported by `GET .../pages`. The image's pixel size is rounded up independently (`ceil(displayed x scale)`), so a coordinate taken from the geometry and an image rounded separately is the double interpretation PoC 6 removed. The geometry endpoint is for layout before the image arrives (aspect-ratio placeholders), for paging, and for knowing the rotation.
    //
    //Future<Uint8List> getAnswerLayoutPageImageTestsTestIdAnswerLayoutPagesPageIndexImageGet(String testId, int pageIndex, { num scale }) async
    test(
        'test getAnswerLayoutPageImageTestsTestIdAnswerLayoutPagesPageIndexImageGet',
        () async {
      // TODO
    });

    // Get Submission Page Image
    //
    // One page of the answer PDF, rasterized by the same pdfium that performs the coordinate transform (PoC 6, approach B).  **A normalized coordinate is built from the returned image's own pixel size, and from nothing else** (`normalized_x = click_px / image_width_px`). pdfium drew the displayed page into those pixels, so that division cannot disagree with this sidecar's coordinate transform.  Do **not** divide by the `displayed_width` / `displayed_height` reported by `GET .../pages`. The image's pixel size is rounded up independently (`ceil(displayed x scale)`), so a coordinate taken from the geometry and an image rounded separately is the double interpretation PoC 6 removed. The geometry endpoint is for layout before the image arrives (aspect-ratio placeholders), for paging, and for knowing the rotation.
    //
    //Future<Uint8List> getSubmissionPageImageSubmissionsSubmissionIdPagesPageIndexImageGet(String submissionId, int pageIndex, { num scale }) async
    test(
        'test getSubmissionPageImageSubmissionsSubmissionIdPagesPageIndexImageGet',
        () async {
      // TODO
    });

    // List Answer Layout Pages
    //
    // Page count, displayed size and rotation of the test's answer sheet, for laying the answer-area editor out **before** the page images arrive, and for paging.  **A normalized coordinate is built from the returned image's own pixel size, and from nothing else** (`normalized_x = click_px / image_width_px`). pdfium drew the displayed page into those pixels, so that division cannot disagree with this sidecar's coordinate transform.  Do **not** divide by the `displayed_width` / `displayed_height` reported by `GET .../pages`. The image's pixel size is rounded up independently (`ceil(displayed x scale)`), so a coordinate taken from the geometry and an image rounded separately is the double interpretation PoC 6 removed. The geometry endpoint is for layout before the image arrives (aspect-ratio placeholders), for paging, and for knowing the rotation.
    //
    //Future<DocumentPagesResponse> listAnswerLayoutPagesTestsTestIdAnswerLayoutPagesGet(String testId) async
    test('test listAnswerLayoutPagesTestsTestIdAnswerLayoutPagesGet', () async {
      // TODO
    });

    // List Submission Pages
    //
    // Page count, displayed size and rotation of the answer PDF, for laying the viewer out **before** the page images arrive, and for paging.  **A normalized coordinate is built from the returned image's own pixel size, and from nothing else** (`normalized_x = click_px / image_width_px`). pdfium drew the displayed page into those pixels, so that division cannot disagree with this sidecar's coordinate transform.  Do **not** divide by the `displayed_width` / `displayed_height` reported by `GET .../pages`. The image's pixel size is rounded up independently (`ceil(displayed x scale)`), so a coordinate taken from the geometry and an image rounded separately is the double interpretation PoC 6 removed. The geometry endpoint is for layout before the image arrives (aspect-ratio placeholders), for paging, and for knowing the rotation.
    //
    //Future<DocumentPagesResponse> listSubmissionPagesSubmissionsSubmissionIdPagesGet(String submissionId) async
    test('test listSubmissionPagesSubmissionsSubmissionIdPagesGet', () async {
      // TODO
    });
  });
}
