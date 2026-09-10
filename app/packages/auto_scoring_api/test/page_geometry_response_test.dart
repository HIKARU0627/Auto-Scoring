import 'package:test/test.dart';
import 'package:auto_scoring_api/auto_scoring_api.dart';

// tests for PageGeometryResponse
void main() {
  final instance = PageGeometryResponseBuilder();
  // TODO add properties to the builder and call build()

  group(PageGeometryResponse, () {
    // Height in PDF points of the page as pdfium displays it (CropBox∩MediaBox, after /Rotate). For sizing a placeholder, not for dividing a click position.
    // num displayedHeight
    test('to test the property `displayedHeight`', () async {
      // TODO
    });

    // Width in PDF points of the page as pdfium displays it (CropBox∩MediaBox, after /Rotate). For sizing a placeholder, not for dividing a click position.
    // num displayedWidth
    test('to test the property `displayedWidth`', () async {
      // TODO
    });

    // 0-based index of this page.
    // int pageIndex
    test('to test the property `pageIndex`', () async {
      // TODO
    });

    // The page's /Rotate, reduced to 0, 90, 180 or 270.
    // int rotation
    test('to test the property `rotation`', () async {
      // TODO
    });
  });
}
