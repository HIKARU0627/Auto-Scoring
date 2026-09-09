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

/// The identity crop (offset 0, scale 1) -- what a question with no
/// confirmed `answer_area` yet effectively has. `_build_answer_image`
/// (backend `adapters/submission_intake.py`) falls back to sending the OCR
/// provider the *entire, uncropped* page image in that case
/// (simplified-design-spec §24 "回答欄検出失敗は…元画像を人間へ提示する"),
/// so its returned boxes are already page-normalized rather than
/// crop-relative -- applying the same offset/scale transform with this
/// rect is a no-op, which is exactly the right behavior for that case.
final NormalizedRectResponse _fullPageArea = NormalizedRectResponse(
  (b) => b
    ..x = 0
    ..y = 0
    ..width = 1
    ..height = 1,
);

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
/// 2. Otherwise, if it names an `anchor_text`, look it up against
///    [recognitions]' OCR bounding boxes (§12.3) -- the same boxes behind
///    the "AI認識文字" Inspector field. Those boxes are normalized against
///    the *cropped answer image* the OCR provider actually saw, not the
///    page, so they are first mapped into page space through
///    [questionAnswerArea] (see [_cropRelativeToPage], P1 review). The
///    caller is responsible for [recognitions] already being scoped to the
///    grading attempt currently on screen -- a re-graded question's history
///    holds one OCR result per attempt, and a stale or not-yet-displayed
///    attempt's result can report the same text at a different position
///    (P2 review; see `QuestionReviewState.recognitionsForDisplayedAttempt`).
/// 3. Anything still unresolved returns `null` -- **nothing is drawn on the
///    answer**, and the caller routes it to the question's comment area
///    instead of guessing (§12.4).
///
/// There is deliberately no fixed-position fallback (Issue #141). A
/// circle/cross/triangle/score whose anchor matched nothing used to be drawn
/// at the question's `score_area`, on the grounds that §12.2 places
/// question-level symbols there -- conflating "the AI meant a mark about the
/// whole question" with "we could not find the words the AI meant". Since
/// Issue #120 derives `score_area` as a band the height of the answer box,
/// every unmatched mark came out as a stroke across a quarter of the page:
/// on the review screen as well as in the export, since this function is
/// what both of them ask. §12.4 already said not to
/// ("無理に本文付近へ配置しない").
NormalizedRectResponse? resolveAnnotationRect({
  required AnnotationResponse annotation,
  required NormalizedRectResponse? questionAnswerArea,
  required List<RecognitionResponse> recognitions,
}) {
  if (annotation.rect != null) return annotation.rect;
  if (annotation.anchorText case final anchorText? when anchorText.isNotEmpty) {
    final matched = _findAnchorTextRect(
      anchorText,
      recognitions,
      _effectiveAnswerArea(questionAnswerArea),
    );
    if (matched != null) return matched;
  }
  return null;
}

/// The answer-area crop to map an OCR box through, treating a `null` *or*
/// degenerate (non-positive width/height) [answerArea] the same way
/// `_build_answer_image` (backend `adapters/submission_intake.py`) does --
/// both mean the OCR provider actually saw the full, uncropped page
/// (simplified-design-spec §24 "回答欄検出失敗は…元画像を人間へ提示する"),
/// so [_fullPageArea]'s identity offset/scale is the correct transform for
/// either. A zero-area `NormalizedRect` is a *valid, persisted* fallback
/// case -- `_build_answer_image`'s own docstring notes the domain model
/// allows one through -- not something this can assume already got
/// rejected upstream; composing a real box's coordinates with a
/// zero-width/height crop instead collapsed every text-anchored annotation
/// to a zero-size rect, making it invisible (P2 review).
NormalizedRectResponse _effectiveAnswerArea(
  NormalizedRectResponse? answerArea,
) {
  if (answerArea == null || answerArea.width <= 0 || answerArea.height <= 0) {
    return _fullPageArea;
  }
  return answerArea;
}

/// The page-normalized rect of the *most recent* OCR word/phrase box whose
/// text exactly matches [anchorText], or `null` if none of [recognitions]'
/// boxes do.
///
/// Searches [recognitions] newest-first (the reverse of its oldest-first
/// server history order): a re-graded question's history holds one OCR
/// recognition per attempt, still present after a later attempt superseded
/// it (append-only), and a stale earlier attempt can report the very same
/// [anchorText] at a *different* position than the current one. Returning
/// the first (oldest) match let a stale attempt's box win outright whenever
/// both happened to contain the anchor text, drawing the annotation over
/// the wrong content even though the Inspector and the annotation itself
/// (`QuestionReviewState.annotationsForDisplayedAttempt`) already show the
/// current attempt (P2 review).
NormalizedRectResponse? _findAnchorTextRect(
  String anchorText,
  List<RecognitionResponse> recognitions,
  NormalizedRectResponse answerArea,
) {
  for (final recognition in recognitions.reversed) {
    for (final box in recognition.boxes) {
      if (box.text == anchorText) {
        return _cropRelativeToPage(box, answerArea);
      }
    }
  }
  return null;
}

/// Maps [box] -- normalized 0..1 against the *cropped answer image* the OCR
/// provider actually saw (`RecognitionJobProcessor` sends it
/// `find_answer_image`'s crop and persists the provider's boxes verbatim,
/// with no reprojection back to page space) -- into a rect normalized
/// against the *whole page*, by composing it with the crop's own
/// page-normalized [answerArea] (`adapters/image/opencv_preprocessor.
/// crop_normalized_rect`: an axis-aligned crop, offset + scale only, no
/// rotation). Copying `box`'s coordinates straight into a page-normalized
/// rect (as if the crop's offset/scale were the identity) placed every
/// text-anchored annotation on the wrong content whenever a question's
/// answer area was smaller than the full page (P1 review).
NormalizedRectResponse _cropRelativeToPage(
  BoundingBoxResponse box,
  NormalizedRectResponse answerArea,
) => NormalizedRectResponse(
  (b) => b
    ..x = answerArea.x + box.x * answerArea.width
    ..y = answerArea.y + box.y * answerArea.height
    ..width = box.width * answerArea.width
    ..height = box.height * answerArea.height,
);
