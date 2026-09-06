import 'dart:ui';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';

/// Converts a 0..1 normalized rectangle (origin top-left, x right / y down --
/// simplified-design-spec.md §5.2, `docs/poc-3-pdf-coordinates.md`) into a
/// pixel [Rect] local to one rendered PDF page of [pageSize].
///
/// `pdfrx`'s `PdfViewerParams.pageOverlaysBuilder` lays each page's overlay
/// `Stack` out at exactly that page's current on-screen size and reports it
/// back as `pageRect`/`page` -- passing that size here keeps overlay
/// placement correct across zoom, scroll, and page rotation without this
/// function ever needing to know the viewer's transform itself (PoC 3,
/// Issue #12, confirmed render scale/DPI drop out of the normalized-to-pixel
/// conversion entirely).
Rect normalizedRectToLocal(NormalizedRectResponse rect, Size pageSize) {
  return Rect.fromLTWH(
    rect.x * pageSize.width,
    rect.y * pageSize.height,
    rect.width * pageSize.width,
    rect.height * pageSize.height,
  );
}
