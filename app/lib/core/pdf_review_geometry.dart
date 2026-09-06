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

/// Annotation kinds placed at a question's fixed "Annotation配置領域"
/// (simplified-design-spec §12.2) rather than at a specific word/phrase --
/// ○・×・△・点数 mark the answer as a whole, not one piece of text in it.
const fixedPositionAnnotationKinds = {'circle', 'cross', 'triangle', 'score'};

/// Resolves [annotation] to the normalized rect it should be drawn at, per
/// simplified-design-spec §12.1-12.4. The AI never proposes coordinates
/// directly (§12.1 "AI自身にPDF座標を直接推測させない...座標決定はアプリ側が
/// 担当する") -- real grading output (`GradingJobProcessor`) always leaves
/// `annotation.rect` unset and names a `target` word/phrase as
/// `anchor_text` instead, for every annotation kind, so this resolution is
/// required for the overlay to ever draw anything against production data
/// (P1 review).
///
/// 1. An annotation that already carries an explicit rect uses it as-is
///    (the API contract allows one; nothing currently sets it, but a future
///    source might).
/// 2. Otherwise, if it names an `anchor_text`, look it up against this
///    question's own OCR bounding boxes (§12.3) -- the same boxes behind
///    the "AI認識文字" Inspector field.
/// 3. Otherwise, a fixed-position mark ([fixedPositionAnnotationKinds])
///    falls back to the question's own `score_area`, its designated
///    "Annotation配置領域" (§12.2).
/// 4. Anything still unresolved returns `null` -- the caller routes it to
///    the question's comment area instead of guessing (§12.4).
NormalizedRectResponse? resolveAnnotationRect({
  required AnnotationResponse annotation,
  required NormalizedRectResponse? questionScoreArea,
  required List<RecognitionResponse> recognitions,
}) {
  if (annotation.rect != null) return annotation.rect;
  if (annotation.anchorText case final anchorText? when anchorText.isNotEmpty) {
    final matched = _findAnchorTextRect(anchorText, recognitions);
    if (matched != null) return matched;
  }
  if (fixedPositionAnnotationKinds.contains(annotation.kind)) {
    return questionScoreArea;
  }
  return null;
}

/// The normalized rect of the first OCR word/phrase box whose text exactly
/// matches [anchorText], or `null` if none of [recognitions]' boxes do.
NormalizedRectResponse? _findAnchorTextRect(
  String anchorText,
  List<RecognitionResponse> recognitions,
) {
  for (final recognition in recognitions) {
    for (final box in recognition.boxes) {
      if (box.text == anchorText) {
        return NormalizedRectResponse(
          (b) => b
            ..x = box.x
            ..y = box.y
            ..width = box.width
            ..height = box.height,
        );
      }
    }
  }
  return null;
}
