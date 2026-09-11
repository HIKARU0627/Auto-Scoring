import 'dart:math' as math;
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
List<NormalizedRectResponse>? resolveAnnotationRects({
  required AnnotationResponse annotation,
  required NormalizedRectResponse? questionAnswerArea,
  required List<RecognitionResponse> recognitions,
}) {
  if (annotation.rect != null) return [annotation.rect!];
  if (annotation.anchorText case final anchorText? when anchorText.isNotEmpty) {
    final matched = _findAnchorTextRects(
      anchorText,
      recognitions,
      _effectiveAnswerArea(questionAnswerArea),
      kind: annotation.kind,
    );
    if (matched != null) return matched;
  }
  return null;
}

NormalizedRectResponse? resolveAnnotationRect({
  required AnnotationResponse annotation,
  required NormalizedRectResponse? questionAnswerArea,
  required List<RecognitionResponse> recognitions,
}) {
  final rects = resolveAnnotationRects(
    annotation: annotation,
    questionAnswerArea: questionAnswerArea,
    recognitions: recognitions,
  );
  if (rects == null || rects.length != 1) return null;
  return rects.first;
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

/// The page-normalized rect of the OCR boxes reading [anchorText], or `null`
/// if none of [recognitions]' boxes do.
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
///
/// **Matching is per *run of boxes*, not per box** (Issue #141). It used to
/// be `box.text == anchorText`, and in the live re-verification that placed
/// *none* of the fourteen annotations -- not one, across eight subjects,
/// with the OCR working. Two structural reasons: an OCR box is one *token*,
/// so an anchor of more than one token (`葉緑体で` is `葉緑体` + `で`) could never
/// equal one box's text; and a token's text carries its own trailing line
/// break, so even a perfectly-read single word did not equal the anchor.
///
/// Must stay identical to `domain/annotation_layout.py`'s
/// `_find_anchor_text_rect` -- the review screen and the PDF export have to
/// agree on where a mark goes (`docs/pdf-export.md` §2).
List<NormalizedRectResponse>? _findAnchorTextRects(
  String anchorText,
  List<RecognitionResponse> recognitions,
  NormalizedRectResponse answerArea, {
  String? kind,
}) {
  final needle = _normalizedForAnchor(anchorText);
  if (needle.isEmpty) return null;
  for (final recognition in recognitions.reversed) {
    final matched = _shortestBoxRun(needle, recognition.boxes, kind: kind);
    if (matched != null) {
      return [
        for (final rect in matched) _cropRelativeToPage(rect, answerArea),
      ];
    }
  }
  return null;
}

List<List<BoundingBoxResponse>> _lineGroups(List<BoundingBoxResponse> boxes) {
  if (boxes.isEmpty) return const [];
  final groups = <List<BoundingBoxResponse>>[
    [boxes.first],
  ];
  for (var index = 1; index < boxes.length; index++) {
    if (_isSameLine(boxes[index - 1], boxes[index])) {
      groups.last.add(boxes[index]);
    } else {
      groups.add([boxes[index]]);
    }
  }
  return groups;
}

/// [text] reduced to what an anchor and an OCR box can be compared on: no
/// whitespace, and full-width ASCII folded to ASCII.
String _normalizedForAnchor(String text) {
  final folded = String.fromCharCodes([
    for (final unit in text.runes)
      if (unit >= 0xFF01 && unit <= 0xFF5E) unit - 0xFEE0 else unit,
  ]);
  return folded.replaceAll(RegExp(r'\s+'), '');
}

/// True if [b2] continues on the same line as [b1] in reading order.
///
/// A token text containing a line break ends the line. Otherwise, two boxes
/// continue the same line if their vertical extent overlaps substantially
/// and x advances forward (horizontal text), or their horizontal extent
/// overlaps substantially and y advances forward (vertical text).
bool _isSameLine(BoundingBoxResponse b1, BoundingBoxResponse b2) {
  if (b1.text.contains('\n')) return false;

  final minH = b1.height < b2.height ? b1.height : b2.height;
  final yOverlap =
      math.min(b1.y + b1.height, b2.y + b2.height) - math.max(b1.y, b2.y);
  final isHoriz =
      minH > 0 && yOverlap > 0.5 * minH && b2.x >= b1.x - b1.width * 0.1;

  final minW = b1.width < b2.width ? b1.width : b2.width;
  final xOverlap =
      math.min(b1.x + b1.width, b2.x + b2.width) - math.max(b1.x, b2.x);
  final isVert =
      minW > 0 && xOverlap > 0.5 * minW && b2.y >= b1.y - b1.height * 0.1;

  return isHoriz || isVert;
}

/// The union rect of the fewest consecutive [boxes] whose joined, normalized
/// text contains [needle] -- or `null` if no run does.
///
/// When the matched run spans across a line break:
/// - Single bounding boxes across line breaks are forbidden (Issue #260).
/// - For CROSS (×): one rect from the anchor's first token line only.
/// - For UNDERLINE / BOX: one rect per line group (Issue #256).
/// - For other kinds: `null` (§12.4 evacuate).
List<NormalizedRectResponse>? _shortestBoxRun(
  String needle,
  Iterable<BoundingBoxResponse> boxesIn, {
  String? kind,
}) {
  final boxes = boxesIn.toList(growable: false);
  final texts = [for (final box in boxes) _normalizedForAnchor(box.text)];
  final limit = _runLengthLimit(needle);
  int? bestStart;
  int? bestEnd;
  for (var start = 0; start < boxes.length; start++) {
    final buffer = StringBuffer();
    for (var end = start; end < boxes.length; end++) {
      buffer.write(texts[end]);
      final joined = buffer.toString();
      if (joined.length > limit) break;
      if (joined.contains(needle)) {
        if (bestStart == null || end - start < bestEnd! - bestStart) {
          bestStart = start;
          bestEnd = end;
        }
        break;
      }
    }
  }
  if (bestStart == null) return null;

  final matchedBoxes = boxes.sublist(bestStart, bestEnd! + 1);
  final lineGroups = _lineGroups(matchedBoxes);
  if (lineGroups.length == 1) {
    return [_unionOfBoxes(matchedBoxes)];
  }

  final isCross = kind?.toLowerCase() == 'cross';
  if (isCross) {
    return [_unionOfBoxes(lineGroups.first)];
  }

  final kindLower = kind?.toLowerCase();
  if (kindLower == 'underline' || kindLower == 'box') {
    return [for (final group in lineGroups) _unionOfBoxes(group)];
  }
  return null;
}

/// How much longer than the anchor a matched run may read. OCR boxes are
/// whole tokens, so a run containing the anchor almost always carries a
/// little more than the anchor itself; twice the anchor plus two characters
/// absorbs that overshoot at every real length seen in the live run while
/// still refusing a box that is mostly not the anchor.
int _runLengthLimit(String needle) => 2 * needle.length + 2;

NormalizedRectResponse _unionOfBoxes(List<BoundingBoxResponse> boxes) {
  var left = boxes.first.x;
  var top = boxes.first.y;
  var right = boxes.first.x + boxes.first.width;
  var bottom = boxes.first.y + boxes.first.height;
  for (final box in boxes.skip(1)) {
    if (box.x < left) left = box.x;
    if (box.y < top) top = box.y;
    if (box.x + box.width > right) right = box.x + box.width;
    if (box.y + box.height > bottom) bottom = box.y + box.height;
  }
  return NormalizedRectResponse(
    (b) => b
      ..x = left
      ..y = top
      // A single box is handed back with its own width/height rather than
      // `x + width - x`, which is not exactly `width` in binary floating
      // point -- one box is by far the commonest run, so recomputing would
      // put rounding noise into nearly every annotation's position.
      ..width = boxes.length == 1 ? boxes.first.width : right - left
      ..height = boxes.length == 1 ? boxes.first.height : bottom - top,
  );
}

/// Maps [rect] -- normalized 0..1 against the *cropped answer image* the OCR
/// provider actually saw (`RecognitionJobProcessor` sends it
/// `find_answer_image`'s crop and persists the provider's boxes verbatim,
/// with no reprojection back to page space) -- into a rect normalized
/// against the *whole page*, by composing it with the crop's own
/// page-normalized [answerArea] (`adapters/image/opencv_preprocessor.
/// crop_normalized_rect`: an axis-aligned crop, offset + scale only, no
/// rotation). Copying the box's coordinates straight into a page-normalized
/// rect (as if the crop's offset/scale were the identity) placed every
/// text-anchored annotation on the wrong content whenever a question's
/// answer area was smaller than the full page (P1 review).
NormalizedRectResponse _cropRelativeToPage(
  NormalizedRectResponse rect,
  NormalizedRectResponse answerArea,
) => NormalizedRectResponse(
  (b) => b
    ..x = answerArea.x + rect.x * answerArea.width
    ..y = answerArea.y + rect.y * answerArea.height
    ..width = rect.width * answerArea.width
    ..height = rect.height * answerArea.height,
);
