import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:pdfrx/pdfrx.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';

/// `Region.label` the sidecar uses for a detected box it could not attribute
/// to any question (`domain.answer_area_detection.UNASSIGNED_QUESTION_LABEL`).
///
/// Duplicated here rather than derived from the API: it is a *value* the two
/// sides agree on, not part of any schema the generator produces, so a change
/// on either side has to be made deliberately on both. `answer_area_editor_test`
/// and the backend's own tests each pin their own side of it.
const unassignedQuestionLabel = '__unassigned__';

/// Shown wherever [unassignedQuestionLabel] would otherwise appear.
const unassignedQuestionDisplayLabel = '設問未割当';

/// The 回答欄 editor: every region of a test's profile drawn on top of the
/// answer sheet they were detected on, editable in place (Issue #105).
///
/// This is the *only* place answer areas are created or changed. Detection
/// (`detectAnswerAreas`) proposes them, and everything a reviewer then does --
/// drawing one by hand, moving it, resizing it, deleting it, or changing which
/// question it belongs to -- happens here, on top of the same page image
/// (Issue #105 acceptance 2 and 6). A separate "add a region" form would mean
/// two ways to define the same thing, and the numbers typed into one of them
/// could never be checked against the page.
///
/// Two states this widget exists to make visible rather than resolve:
///
/// * **未検出** -- a confirmed question with no box. Listed as chips above the
///   pages, and tapping one arms it as the next box to draw. It does not block
///   confirming: a question with no area still grades, against the whole page,
///   and lands on the review screen saying so.
/// * **設問未割当** -- a box the AI found but could not attribute. Drawn in the
///   [AppStatusTone.attention] tone, listed first, and it *does* block
///   confirming, because nothing downstream would ever mention it again.
///
/// The AI's proposal is never treated as final: every box arrives unconfirmed
/// and is editable until the reviewer confirms the profile as a whole.
class AnswerAreaEditor extends StatefulWidget {
  const AnswerAreaEditor({
    required this.pages,
    required this.regions,
    required this.questionNumbers,
    required this.undetectedQuestionNumbers,
    required this.absentQuestionNumbers,
    required this.readingOrderConflicts,
    required this.onRegionsChanged,
    required this.readOnly,
    this.pdfBytes,
    this.onEditNumerically,
    super.key,
  });

  /// One entry per page of the answer sheet, in order -- the page's own
  /// dimensions in points. Only the *ratio* is used (to lay each page out at
  /// its true shape); normalized coordinates make the absolute size and the
  /// render DPI drop out entirely, exactly as PoC 3 established.
  final List<PageFormatModel> pages;

  final List<RegionModel> regions;

  /// The questions a box may be assigned to -- this test's confirmed question
  /// set. Empty until the 配点と採点基準 has been confirmed, which is also when
  /// detection becomes possible at all.
  final List<String> questionNumbers;

  final List<String> undetectedQuestionNumbers;

  /// Questions detection reported as having no answer space anywhere on this
  /// sheet (Issue #164).
  ///
  /// Kept apart from [undetectedQuestionNumbers] because the two ask the
  /// reviewer for opposite things: an undetected question needs its box
  /// drawn, and an absent one needs the 採点基準 or the registered sheet
  /// fixed -- drawing a box for it would invent one. Measured on the real
  /// material, the absent case is by far the more common of the two (26 of
  /// 37 questions in one run), and showing both under one "not found"
  /// heading is what led this Issue's reporter to measure the wrong
  /// denominator.
  ///
  /// Still editable: a number listed here is drawn as a chip like any other,
  /// because the reviewer can see the page and the model is not always
  /// right. Drawing the box takes it out of both lists.
  final List<String> absentQuestionNumbers;

  /// Pairs of question numbers whose boxes sit in the opposite order to
  /// their numbers on the page they share (Issue #171).
  ///
  /// The one failure on this screen that looks like success: every question
  /// has a box, so nothing is undetected and the banner above says so, while
  /// two questions have each other's answer. Measured on the real material
  /// it happened every run on one subject and produced two grades of 0 at
  /// high confidence, both approved by a person.
  ///
  /// Shown, never acted on: which of the two boxes is the misplaced one is
  /// not decidable from the geometry, so the app offers the swap and the
  /// reviewer decides. It does not block confirming -- the check is a
  /// measured rule of thumb over 8 answer sheets, and a wrong flag must not
  /// be able to make a correct profile unconfirmable.
  final List<List<String>> readingOrderConflicts;

  /// The answer sheet itself. `null` renders the pages as empty outlines at
  /// the right shape -- which is what a reviewer sees before uploading a
  /// sheet, and what a widget test drives without needing PDFium.
  final Uint8List? pdfBytes;

  final ValueChanged<List<RegionModel>> onRegionsChanged;

  /// Opens the numeric region dialog for one region. Supplied by the settings
  /// screen, which already owns that dialog -- it is how every field of a
  /// region stays reachable without a pointer (a box can be positioned by
  /// typing four numbers), and how the non-回答欄 region kinds keep their
  /// free-text label.
  final void Function(int index)? onEditNumerically;

  /// A confirmed profile is immutable: everything is drawn, nothing moves.
  final bool readOnly;

  @override
  State<AnswerAreaEditor> createState() => _AnswerAreaEditorState();
}

class _AnswerAreaEditorState extends State<AnswerAreaEditor> {
  /// Which region is selected for direct manipulation, by index into
  /// [AnswerAreaEditor.regions].
  ///
  /// By index, not by `region_id`, because every callback out of this widget
  /// is already index-based and nothing here guarantees a profile's ids are
  /// distinct -- the sidecar rejects a duplicate id since Issue #105, but a
  /// profile saved before that can still hold one, and keying a selection (or
  /// a widget) on a repeated id crashes the whole screen rather than
  /// degrading. Cleared whenever the region set changes length, since an
  /// index into the old list means something else in the new one.
  int? _selectedIndex;

  /// The question a newly drawn box is assigned to. Defaults to the first
  /// still-undetected question, so the common action -- "問3 was missed, draw
  /// it" -- is one drag with nothing else to set. Falls back to
  /// [unassignedQuestionLabel] once every question has a box.
  String? _drawTarget;

  /// The in-progress drag, in normalized page coordinates, and the page it is
  /// on. Kept in state (not painted directly) so the preview rectangle and
  /// the committed region are produced by exactly the same math.
  int? _draftPageIndex;
  Offset? _draftStart;
  Offset? _draftEnd;

  @override
  void didUpdateWidget(AnswerAreaEditor oldWidget) {
    super.didUpdateWidget(oldWidget);
    final index = _selectedIndex;
    if (index != null && index >= widget.regions.length) {
      // Only when the index no longer addresses anything -- a reload that
      // returned fewer regions. Clearing on *any* length change would also
      // clear the selection this widget just set on a box the reviewer drew,
      // since the parent rebuilds with the longer list a frame later.
      _selectedIndex = null;
    }
  }

  String get _effectiveDrawTarget {
    final target = _drawTarget;
    if (target != null &&
        (target == unassignedQuestionLabel ||
            widget.questionNumbers.contains(target))) {
      return target;
    }
    // Falls through to the absent group when nothing is undetected
    // (Issue #167): on one measured subject *every* question with no box is
    // in that group, and leaving the target on 「割り当てなし」 there would
    // make the way out one click longer than the screen says it is.
    if (widget.undetectedQuestionNumbers.isNotEmpty) {
      return widget.undetectedQuestionNumbers.first;
    }
    if (widget.absentQuestionNumbers.isNotEmpty) {
      return widget.absentQuestionNumbers.first;
    }
    return unassignedQuestionLabel;
  }

  void _emit(List<RegionModel> next) => widget.onRegionsChanged(next);

  void _replaceRegion(int index, RegionModel region) {
    final next = [...widget.regions];
    next[index] = region;
    _emit(next);
  }

  void _deleteRegion(int index) {
    final next = [...widget.regions]..removeAt(index);
    // Cleared explicitly: every later index shifts down by one, so keeping
    // the selection would move the highlight onto a box nobody selected.
    setState(() => _selectedIndex = null);
    _emit(next);
  }

  /// A region id that no current region uses.
  ///
  /// Detection names its own regions `answer-area-N`, so a hand-drawn box
  /// must not be able to collide with one: two regions sharing an id would
  /// make the selection, and the numeric-edit dialog, address the wrong box.
  String _freeRegionId() {
    final taken = widget.regions.map((r) => r.regionId).toSet();
    var index = 0;
    while (taken.contains('manual-answer-area-$index')) {
      index++;
    }
    return 'manual-answer-area-$index';
  }

  void _commitDraft() {
    final pageIndex = _draftPageIndex;
    final start = _draftStart;
    final end = _draftEnd;
    setState(() {
      _draftPageIndex = null;
      _draftStart = null;
      _draftEnd = null;
    });
    if (pageIndex == null || start == null || end == null) return;
    final bbox = _bboxFrom(start, end);
    // A tap, or a drag so small it is really a tap, is not an attempt to draw
    // a box -- committing it would litter the page with slivers the reviewer
    // then has to find and delete.
    if (bbox == null) return;
    final regionId = _freeRegionId();
    _emit([
      ...widget.regions,
      RegionModel(
        (b) => b
          ..regionId = regionId
          ..kind = RegionKind.answerArea
          ..pageIndex = pageIndex
          ..label = _effectiveDrawTarget
          ..confirmed = false
          ..bbox.replace(bbox),
      ),
    ]);
    setState(() => _selectedIndex = widget.regions.length);
  }

  /// The normalized box two drag points describe, or `null` when it is too
  /// small to be a deliberate rectangle.
  NormalizedBBoxModel? _bboxFrom(Offset a, Offset b) {
    final x0 = math.min(a.dx, b.dx).clamp(0.0, 1.0).toDouble();
    final x1 = math.max(a.dx, b.dx).clamp(0.0, 1.0).toDouble();
    final y0 = math.min(a.dy, b.dy).clamp(0.0, 1.0).toDouble();
    final y1 = math.max(a.dy, b.dy).clamp(0.0, 1.0).toDouble();
    if (x1 - x0 < _minimumBoxSize || y1 - y0 < _minimumBoxSize) return null;
    return NormalizedBBoxModel(
      (builder) => builder
        ..x0 = x0
        ..y0 = y0
        ..x1 = x1
        ..y1 = y1,
    );
  }

  /// Move or resize one region by a normalized delta, keeping it on the page
  /// and never letting it collapse.
  ///
  /// Clamped rather than rejected: a drag that runs off the edge of the page
  /// should stop at the edge, which is what a reviewer expects, instead of
  /// snapping back or producing a box the sidecar will refuse.
  void _nudgeRegion(int index, {required Offset delta, required bool resize}) {
    final region = widget.regions[index];
    final bbox = region.bbox;
    // The generated model types these as `num` (the OpenAPI schema says
    // "number"), so they are widened once here rather than at every use.
    double x0 = bbox.x0.toDouble();
    double y0 = bbox.y0.toDouble();
    double x1 = bbox.x1.toDouble();
    double y1 = bbox.y1.toDouble();
    if (resize) {
      x1 = (x1 + delta.dx).clamp(x0 + _minimumBoxSize, 1.0).toDouble();
      y1 = (y1 + delta.dy).clamp(y0 + _minimumBoxSize, 1.0).toDouble();
    } else {
      final width = x1 - x0;
      final height = y1 - y0;
      x0 = (x0 + delta.dx).clamp(0.0, 1.0 - width).toDouble();
      y0 = (y0 + delta.dy).clamp(0.0, 1.0 - height).toDouble();
      x1 = x0 + width;
      y1 = y0 + height;
    }
    _replaceRegion(
      index,
      region.rebuild(
        (b) => b.bbox.replace(
          NormalizedBBoxModel(
            (builder) => builder
              ..x0 = x0
              ..y0 = y0
              ..x1 = x1
              ..y1 = y1,
          ),
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        _buildUndetectedBanner(context),
        if (widget.readingOrderConflicts.isNotEmpty) ...[
          const SizedBox(height: AppSpacing.md),
          _buildReadingOrderWarning(context),
        ],
        if (!widget.readOnly) ...[
          const SizedBox(height: AppSpacing.md),
          _buildDrawToolbar(context),
        ],
        const SizedBox(height: AppSpacing.md),
        for (var pageIndex = 0; pageIndex < widget.pages.length; pageIndex++)
          Padding(
            padding: const EdgeInsets.only(bottom: AppSpacing.lg),
            child: _buildPage(context, pageIndex),
          ),
        _buildRegionList(context),
      ],
    );
  }

  Widget _buildReadingOrderWarning(BuildContext context) {
    return Column(
      key: const Key('answer-area-reading-order'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(
              Icons.swap_vert,
              size: AppIconSize.dense,
              color: AppStatusTone.attention.color(context),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Text(
                // Says what was observed, not what is wrong: the geometry
                // cannot say which of the two boxes moved.
                '設問の並び順と、回答欄の位置の順序が食い違っています。'
                '回答欄が入れ替わっていると、それぞれ相手の解答が採点されます。'
                '答案を見て、正しければそのまま進んでください。',
                style: context.texts.bodyMedium,
              ),
            ),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        for (final pair in widget.readingOrderConflicts)
          if (pair.length == 2)
            Padding(
              padding: const EdgeInsets.only(bottom: AppSpacing.xs),
              child: Row(
                children: [
                  Expanded(
                    child: Text(
                      '${pair[0]} と ${pair[1]}',
                      style: context.texts.bodyMedium?.copyWith(
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ),
                  TextButton.icon(
                    key: Key('answer-area-swap-${pair[0]}-${pair[1]}'),
                    onPressed: widget.readOnly
                        ? null
                        : () => _swapLabels(pair[0], pair[1]),
                    icon: const Icon(
                      Icons.swap_horiz,
                      size: AppIconSize.inline,
                    ),
                    label: const Text('回答欄を入れ替える'),
                  ),
                ],
              ),
            ),
      ],
    );
  }

  /// Move each of the two questions onto the other's boxes.
  ///
  /// A relabel, not a move: the rectangles stay exactly where the page
  /// prints them, which is the half detection got right. Nothing is saved
  /// until the reviewer saves, so pressing it twice is its own undo.
  void _swapLabels(String first, String second) {
    _emit([
      for (final region in widget.regions)
        if (region.kind == RegionKind.answerArea && region.label == first)
          region.rebuild((b) => b.label = second)
        else if (region.kind == RegionKind.answerArea && region.label == second)
          region.rebuild((b) => b.label = first)
        else
          region,
    ]);
  }

  Widget _buildUndetectedBanner(BuildContext context) {
    final undetected = widget.undetectedQuestionNumbers;
    if (widget.questionNumbers.isEmpty) {
      return Text(
        '配点と採点基準がまだ確定していないので、回答欄を割り当てる設問がありません。'
        '先に配点と採点基準を確定してください。',
        key: const Key('answer-area-no-questions'),
        style: context.texts.bodyMedium,
      );
    }
    final absent = widget.absentQuestionNumbers;
    if (undetected.isEmpty && absent.isEmpty) {
      return Row(
        key: const Key('answer-area-all-detected'),
        children: [
          Icon(
            Icons.check_circle_outline,
            size: AppIconSize.dense,
            color: AppStatusTone.success.color(context),
          ),
          const SizedBox(width: AppSpacing.sm),
          Expanded(
            child: Text(
              '${widget.questionNumbers.length}件の設問すべてに回答欄があります。',
              style: context.texts.bodyMedium,
            ),
          ),
        ],
      );
    }
    return Column(
      key: const Key('answer-area-undetected'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        if (undetected.isNotEmpty)
          _buildMissingGroup(
            context,
            keyPrefix: 'answer-area-undetected',
            icon: Icons.error_outline,
            // Named as "not found", never as "none exists": the boxes are
            // on the page, this run did not locate them.
            message:
                '回答欄が見つからなかった設問が${undetected.length}件あります。'
                'このまま確定もできますが、その設問は答案のページ全体を採点に送り、'
                '要確認として人の目に回ります。',
            action: '答案には回答欄があるはずです。設問名を押して枠を引いてください。',
            numbers: undetected,
          ),
        if (undetected.isNotEmpty && absent.isNotEmpty)
          const SizedBox(height: AppSpacing.md),
        if (absent.isNotEmpty)
          _buildMissingGroup(
            context,
            keyPrefix: 'answer-area-absent',
            icon: Icons.description_outlined,
            // Says what is known, not what was concluded (Issue #167).
            //
            // This used to open with 「回答欄が無いと判定された」. Measured over
            // the real material the claim is right far more often than not,
            // but not always -- one subject's smallest answer box has an
            // outline the scan breaks (its top rule is 61% inked), so it
            // never becomes a candidate and the model can only report the
            // question as absent. A reviewer told that as a fact goes to the
            // 採点基準, finds nothing, and has lost the time.
            //
            // The likelihood is carried by the *order* of the two actions,
            // never by a number. A measured ratio printed here would be a
            // property of one set of teaching material at one moment; on the
            // screen it would go stale with nobody noticing. It lives in
            // docs/answer-area-detection.md with the date it was taken.
            message:
                'この答案では回答欄を見つけられなかった設問が${absent.length}件あります。'
                '登録した答案が課題の一部のページで、採点基準がそれより広い範囲を'
                '含んでいることがあります。まず答案と採点基準を確かめてください。',
            // Not a trailing sentence (Issue #167). Softening the opening
            // promotes this from a footnote to the other real possibility,
            // and it is the only path by which "a person fixes what
            // detection could not, but only then" actually works. A question
            // wrongly listed here is not a dead end as long as the way out
            // is visible.
            action: '答案に回答欄があるのに挙がっているときは、設問名を押して枠を引いてください。',
            numbers: absent,
          ),
      ],
    );
  }

  Widget _buildMissingGroup(
    BuildContext context, {
    required String keyPrefix,
    required IconData icon,
    required String message,
    required String action,
    required List<String> numbers,
  }) {
    return Column(
      key: Key('$keyPrefix-group'),
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Icon(
              icon,
              size: AppIconSize.dense,
              color: AppStatusTone.attention.color(context),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(child: Text(message, style: context.texts.bodyMedium)),
          ],
        ),
        const SizedBox(height: AppSpacing.sm),
        // Immediately above the chips it describes, and in its own emphasis
        // rather than inside the paragraph: this is the sentence the
        // reviewer has to act on, and the chips below are the action.
        Text(
          action,
          key: Key('$keyPrefix-action'),
          style: context.texts.bodyMedium?.copyWith(
            fontWeight: FontWeight.w600,
          ),
        ),
        const SizedBox(height: AppSpacing.xs),
        Wrap(
          spacing: AppSpacing.sm,
          runSpacing: AppSpacing.xs,
          children: [
            for (final number in numbers)
              ActionChip(
                key: Key('$keyPrefix-$number'),
                avatar: const Icon(
                  Icons.edit_outlined,
                  size: AppIconSize.inline,
                ),
                label: Text(number),
                onPressed: widget.readOnly
                    ? null
                    : () => setState(() => _drawTarget = number),
              ),
          ],
        ),
      ],
    );
  }

  Widget _buildDrawToolbar(BuildContext context) {
    final target = _effectiveDrawTarget;
    return Row(
      children: [
        Text('次に引く回答欄の設問:', style: context.texts.bodyMedium),
        const SizedBox(width: AppSpacing.sm),
        DropdownButton<String>(
          key: const Key('answer-area-draw-target'),
          value: target,
          onChanged: (value) => setState(() => _drawTarget = value),
          items: [
            for (final number in widget.questionNumbers)
              DropdownMenuItem(value: number, child: Text(number)),
            const DropdownMenuItem(
              value: unassignedQuestionLabel,
              child: Text(unassignedQuestionDisplayLabel),
            ),
          ],
        ),
        const SizedBox(width: AppSpacing.md),
        Expanded(
          child: Text(
            '答案の上をドラッグすると回答欄を引けます。枠を選ぶと動かせます。',
            style: context.texts.bodySmall,
          ),
        ),
      ],
    );
  }

  Widget _buildPage(BuildContext context, int pageIndex) {
    final page = widget.pages[pageIndex];
    final aspectRatio = page.heightPt > 0 ? page.widthPt / page.heightPt : 1.0;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('${pageIndex + 1}ページ', style: context.texts.labelLarge),
        const SizedBox(height: AppSpacing.xs),
        ConstrainedBox(
          constraints: const BoxConstraints(maxWidth: _maxPageWidth),
          child: AspectRatio(
            aspectRatio: aspectRatio,
            child: LayoutBuilder(
              builder: (context, constraints) => Stack(
                fit: StackFit.expand,
                children: [
                  _buildPageBackground(context, pageIndex),
                  _buildDrawSurface(context, pageIndex, constraints.biggest),
                  ..._buildRegionOverlays(
                    context,
                    pageIndex,
                    constraints.biggest,
                  ),
                  if (_draftPageIndex == pageIndex)
                    _buildDraftPreview(context, constraints.biggest),
                ],
              ),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildPageBackground(BuildContext context, int pageIndex) {
    final bytes = widget.pdfBytes;
    final border = Border.all(color: context.colors.outlineVariant);
    if (bytes == null) {
      return DecoratedBox(
        key: Key('answer-area-page-placeholder-$pageIndex'),
        decoration: BoxDecoration(
          color: context.colors.surface,
          border: border,
        ),
      );
    }
    return DecoratedBox(
      decoration: BoxDecoration(border: border),
      child: PdfDocumentViewBuilder(
        documentRef: PdfDocumentRefData(bytes, sourceName: 'answer-layout'),
        builder: (context, document) => PdfPageView(
          key: Key('answer-area-page-$pageIndex'),
          document: document,
          pageNumber: pageIndex + 1,
          // The page's shape is already fixed by the enclosing AspectRatio,
          // and the drop shadow would sit between the page and the boxes
          // drawn on it.
          decoration: const BoxDecoration(),
        ),
      ),
    );
  }

  /// The transparent layer that turns a drag into a new region.
  ///
  /// Sits *under* the region overlays so a drag that starts on an existing box
  /// moves that box instead of drawing a new one on top of it.
  Widget _buildDrawSurface(BuildContext context, int pageIndex, Size size) {
    if (widget.readOnly) return const SizedBox.shrink();
    Offset normalize(Offset local) => Offset(
      (local.dx / size.width).clamp(0.0, 1.0).toDouble(),
      (local.dy / size.height).clamp(0.0, 1.0).toDouble(),
    );
    return Positioned.fill(
      child: GestureDetector(
        key: Key('answer-area-draw-surface-$pageIndex'),
        behavior: HitTestBehavior.opaque,
        onTap: () => setState(() => _selectedIndex = null),
        // `onPanDown`, not `onPanStart`: a pan is only *accepted* once the
        // pointer has travelled past the drag slop, and `onPanStart` reports
        // the position at that moment -- so a box drawn from it would start
        // ~18 logical pixels from where the reviewer actually pressed, in
        // whichever direction they happened to move first. `onPanDown` fires
        // at the press itself. A press that turns out to be a tap is
        // harmless: `_commitDraft` discards anything too small to be a
        // deliberate rectangle.
        onPanDown: (details) => setState(() {
          _draftPageIndex = pageIndex;
          _draftStart = normalize(details.localPosition);
          _draftEnd = _draftStart;
        }),
        onPanUpdate: (details) =>
            setState(() => _draftEnd = normalize(details.localPosition)),
        onPanEnd: (_) => _commitDraft(),
        onPanCancel: _commitDraft,
      ),
    );
  }

  Widget _buildDraftPreview(BuildContext context, Size size) {
    final start = _draftStart;
    final end = _draftEnd;
    if (start == null || end == null) return const SizedBox.shrink();
    final left = math.min(start.dx, end.dx) * size.width;
    final top = math.min(start.dy, end.dy) * size.height;
    return Positioned(
      left: left,
      top: top,
      width: (start.dx - end.dx).abs() * size.width,
      height: (start.dy - end.dy).abs() * size.height,
      child: IgnorePointer(
        child: DecoratedBox(
          decoration: BoxDecoration(
            border: Border.all(color: context.colors.primary, width: 2),
          ),
        ),
      ),
    );
  }

  List<Widget> _buildRegionOverlays(
    BuildContext context,
    int pageIndex,
    Size size,
  ) {
    final widgets = <Widget>[];
    for (var index = 0; index < widget.regions.length; index++) {
      final region = widget.regions[index];
      if (region.pageIndex != pageIndex) continue;
      final selected = index == _selectedIndex;
      final left = region.bbox.x0 * size.width;
      final top = region.bbox.y0 * size.height;
      final width = (region.bbox.x1 - region.bbox.x0) * size.width;
      final height = (region.bbox.y1 - region.bbox.y0) * size.height;
      widgets.add(
        Positioned(
          left: left,
          top: top,
          width: width,
          height: height,
          child: _RegionBox(
            index: index,
            region: region,
            selected: selected,
            readOnly: widget.readOnly,
            onSelect: () => setState(() => _selectedIndex = index),
            onMove: (delta) => _nudgeRegion(
              index,
              delta: Offset(delta.dx / size.width, delta.dy / size.height),
              resize: false,
            ),
            onResize: (delta) => _nudgeRegion(
              index,
              delta: Offset(delta.dx / size.width, delta.dy / size.height),
              resize: true,
            ),
          ),
        ),
      );
    }
    return widgets;
  }

  Widget _buildRegionList(BuildContext context) {
    if (widget.regions.isEmpty) {
      return Text(
        '領域はまだありません。',
        key: const Key('answer-area-empty'),
        style: context.texts.bodyMedium,
      );
    }
    // Unassigned boxes first: they are the only thing here that stops the
    // profile being confirmed, so they must not be somewhere down a long list.
    final order = List<int>.generate(widget.regions.length, (i) => i)
      ..sort((a, b) {
        final unassignedA = _isUnassigned(widget.regions[a]) ? 0 : 1;
        final unassignedB = _isUnassigned(widget.regions[b]) ? 0 : 1;
        if (unassignedA != unassignedB) return unassignedA - unassignedB;
        return a - b;
      });
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [for (final index in order) _buildRegionRow(context, index)],
    );
  }

  Widget _buildRegionRow(BuildContext context, int index) {
    final region = widget.regions[index];
    final unassigned = _isUnassigned(region);
    final isAnswerArea = region.kind == RegionKind.answerArea;
    return Card(
      key: Key('answer-area-row-$index'),
      margin: const EdgeInsets.only(bottom: AppSpacing.sm),
      child: Padding(
        padding: AppSpacing.card,
        child: Row(
          children: [
            Icon(
              unassigned ? Icons.help_outline : Icons.crop_free,
              size: AppIconSize.dense,
              color: unassigned
                  ? AppStatusTone.attention.color(context)
                  : AppStatusTone.neutral.color(context),
            ),
            const SizedBox(width: AppSpacing.sm),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${_regionKindLabel(region.kind)}・${region.pageIndex + 1}ページ',
                    style: context.texts.bodyMedium,
                  ),
                  if (region.text != null && region.text!.isNotEmpty)
                    Text(
                      region.text!,
                      key: Key('answer-area-note-$index'),
                      style: context.texts.bodySmall,
                    ),
                ],
              ),
            ),
            if (isAnswerArea)
              DropdownButton<String>(
                key: Key('answer-area-question-$index'),
                value: _dropdownValue(region.label),
                onChanged: widget.readOnly
                    ? null
                    : (value) {
                        if (value == null) return;
                        _replaceRegion(
                          index,
                          region.rebuild((b) => b.label = value),
                        );
                      },
                items: [
                  for (final number in widget.questionNumbers)
                    DropdownMenuItem(value: number, child: Text(number)),
                  const DropdownMenuItem(
                    value: unassignedQuestionLabel,
                    child: Text(unassignedQuestionDisplayLabel),
                  ),
                ],
              )
            else
              Text(region.label, style: context.texts.bodyMedium),
            if (widget.onEditNumerically != null)
              IconButton(
                key: Key('answer-area-edit-$index'),
                tooltip: '数値で編集',
                icon: const Icon(Icons.tune),
                onPressed: widget.readOnly
                    ? null
                    : () => widget.onEditNumerically!(index),
              ),
            IconButton(
              key: Key('answer-area-delete-$index'),
              tooltip: '削除',
              icon: const Icon(Icons.delete_outline),
              onPressed: widget.readOnly ? null : () => _deleteRegion(index),
            ),
          ],
        ),
      ),
    );
  }

  /// The dropdown value for a region's label.
  ///
  /// A label that matches no current question (a test whose 配点 was
  /// re-confirmed with different numbers, or a region typed in by hand)
  /// falls back to [unassignedQuestionLabel] so the dropdown still has a
  /// selectable value -- and so the region reads as what it now is: attached
  /// to no question, and blocking confirmation until someone says which.
  String _dropdownValue(String label) =>
      widget.questionNumbers.contains(label) ? label : unassignedQuestionLabel;

  bool _isUnassigned(RegionModel region) =>
      region.kind == RegionKind.answerArea &&
      !widget.questionNumbers.contains(region.label);
}

/// One region drawn on the page: a labelled outline, draggable when selected.
class _RegionBox extends StatelessWidget {
  const _RegionBox({
    required this.index,
    required this.region,
    required this.selected,
    required this.readOnly,
    required this.onSelect,
    required this.onMove,
    required this.onResize,
  });

  final int index;
  final RegionModel region;
  final bool selected;
  final bool readOnly;
  final VoidCallback onSelect;
  final ValueChanged<Offset> onMove;
  final ValueChanged<Offset> onResize;

  @override
  Widget build(BuildContext context) {
    final unassigned =
        region.kind == RegionKind.answerArea &&
        region.label == unassignedQuestionLabel;
    // Never colour alone: the label text and the dashed-vs-solid weight carry
    // the same distinction (Issue #25's non-colour-dependent rule).
    final tone = unassigned ? AppStatusTone.attention : AppStatusTone.neutral;
    final color = unassigned ? tone.color(context) : context.colors.primary;
    return GestureDetector(
      key: Key('answer-area-box-$index'),
      behavior: HitTestBehavior.opaque,
      onTap: onSelect,
      onPanStart: readOnly ? null : (_) => onSelect(),
      onPanUpdate: readOnly ? null : (details) => onMove(details.delta),
      child: Stack(
        fit: StackFit.expand,
        children: [
          DecoratedBox(
            decoration: BoxDecoration(
              border: Border.all(color: color, width: selected ? 3 : 1.5),
              color: color.withValues(alpha: selected ? 0.12 : 0.06),
            ),
          ),
          Positioned(
            left: AppSpacing.xs / 2,
            top: AppSpacing.xs / 2,
            child: DecoratedBox(
              decoration: BoxDecoration(
                color: context.colors.surface.withValues(alpha: 0.85),
                borderRadius: AppRadius.smAll,
              ),
              child: Padding(
                padding: const EdgeInsets.symmetric(horizontal: AppSpacing.xs),
                child: Text(
                  unassigned
                      ? unassignedQuestionDisplayLabel
                      : region.label.isEmpty
                      ? _regionKindLabel(region.kind)
                      : region.label,
                  style: context.texts.labelSmall?.copyWith(color: color),
                ),
              ),
            ),
          ),
          if (selected && !readOnly)
            Positioned(
              right: 0,
              bottom: 0,
              child: GestureDetector(
                key: Key('answer-area-resize-$index'),
                behavior: HitTestBehavior.opaque,
                onPanUpdate: (details) => onResize(details.delta),
                child: Container(
                  width: _handleSize,
                  height: _handleSize,
                  color: color,
                ),
              ),
            ),
        ],
      ),
    );
  }
}

String _regionKindLabel(RegionKind kind) => switch (kind) {
  RegionKind.question => '問題文',
  RegionKind.answerArea => '回答欄',
  RegionKind.annotationArea => '添削記号領域',
  RegionKind.score => '配点',
  RegionKind.rubric => '採点基準',
  RegionKind.modelAnswer => '模範解答',
  _ => kind.name,
};

/// Smallest box a drag may produce, as a fraction of the page. Below this a
/// drag is a tap that slipped, not a rectangle -- and the sidecar rejects a
/// zero-area box outright.
const double _minimumBoxSize = 0.01;

/// Side of the resize handle, in logical pixels.
const double _handleSize = 14;

/// Widest a page is drawn. A full-width A4 on a desktop monitor is taller
/// than the screen, which makes drawing a box a scroll-and-guess exercise.
const double _maxPageWidth = 720;
