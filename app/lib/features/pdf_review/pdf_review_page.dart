import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:pdfrx/pdfrx.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/confidence_level.dart';
import 'package:auto_scoring_app/core/pdf_review_geometry.dart';

/// 添削レビュー画面 (simplified-design-specification.md §16.5, Issue #21).
///
/// Shows the original answer PDF with AI recognition/score/rubric/confidence
/// and annotations for the selected question side by side: Navigation Rail
/// (設問一覧) + `pdfrx` PDF viewer with a widget overlay for annotations that
/// carry a target Bounding Box + Inspector (認識文字/点数/根拠/採点基準/
/// confidence) + a bottom action bar. The original PDF is never edited --
/// annotations are drawn as widgets on top of it (§13.1).
///
/// Approving/rejecting/editing a question here only updates this screen's own
/// in-memory state; persisting a reviewer's decision and generating the final
/// corrected PDF are out of scope for Issue #21 (its "対象外") and are a
/// later issue's job. See `docs/pdf-review-overlay.md` for the full list of
/// decisions/open questions this screen relies on.
///
/// `features` may depend on `core` and `api` (see `AGENTS.md` "Architecture").
class PdfReviewPage extends StatefulWidget {
  const PdfReviewPage({
    super.key,
    required this.dependencies,
    required this.testId,
    required this.submissionId,
  });

  final AppDependencies dependencies;
  final String testId;
  final String submissionId;

  @override
  State<PdfReviewPage> createState() => _PdfReviewPageState();
}

/// A reviewer's decision for one question, kept only in this screen's memory
/// (Issue #21 "対象外": no persistence).
enum ReviewDecision { pending, approved, rejected }

/// Everything fetched (or being fetched) for one question, plus the
/// reviewer's local-only decision and note.
class QuestionReviewState {
  List<RecognitionResponse>? recognitions;
  List<GradeResultResponse>? grades;
  List<AnnotationResponse>? annotations;
  String? error;
  bool loading = false;
  ReviewDecision decision = ReviewDecision.pending;
  String note = '';

  bool get hasLoaded =>
      recognitions != null && grades != null && annotations != null;

  /// Annotations with a target Bounding Box -- drawn on the PDF overlay.
  List<AnnotationResponse> get placedAnnotations =>
      (annotations ?? const []).where((a) => a.rect != null).toList();

  /// Annotations pdfrx cannot place (no target Bounding Box, or only an
  /// `anchor_text` this screen does not yet resolve to a page position) --
  /// they retreat to the question's comment area instead of being dropped
  /// (simplified-design-spec.md §12.4). See `docs/pdf-review-overlay.md`.
  List<AnnotationResponse> get fallbackAnnotations =>
      (annotations ?? const []).where((a) => a.rect == null).toList();

  RecognitionResponse? get latestRecognition =>
      recognitions == null || recognitions!.isEmpty ? null : recognitions!.last;

  GradeResultResponse? get latestGrade =>
      grades == null || grades!.isEmpty ? null : grades!.last;
}

class _PdfReviewPageState extends State<PdfReviewPage> {
  late final PdfViewerController _pdfController;
  final _noteController = TextEditingController();
  final _noteFocusNode = FocusNode(debugLabel: '修正コメント');

  bool _loadingShell = true;
  String? _shellError;
  SubmissionResponse? _submission;
  List<QuestionResponse> _questions = const [];
  Uint8List? _pdfBytes;
  int _questionIndex = 0;
  final Map<String, QuestionReviewState> _reviews = {};

  @override
  void initState() {
    super.initState();
    _pdfController = PdfViewerController();
    _loadShell();
  }

  @override
  void dispose() {
    _noteController.dispose();
    _noteFocusNode.dispose();
    super.dispose();
  }

  QuestionResponse? get _currentQuestion =>
      _questionIndex >= 0 && _questionIndex < _questions.length
      ? _questions[_questionIndex]
      : null;

  QuestionReviewState? get _currentReview {
    final question = _currentQuestion;
    if (question == null) return null;
    return _reviews[question.id];
  }

  Future<void> _loadShell() async {
    setState(() {
      _loadingShell = true;
      _shellError = null;
    });
    try {
      final submission = await widget.dependencies.getSubmission(
        widget.submissionId,
      );
      final questions = await widget.dependencies.listQuestions(widget.testId);
      final pdfBytes = await widget.dependencies.getSourcePdf(
        widget.submissionId,
      );
      final sorted = questions.toList()
        ..sort((a, b) {
          final byPage = a.page.compareTo(b.page);
          return byPage != 0 ? byPage : a.number.compareTo(b.number);
        });
      if (!mounted) return;
      setState(() {
        _submission = submission;
        _questions = sorted;
        _pdfBytes = pdfBytes;
        _questionIndex = 0;
      });
      unawaited(_ensureReviewLoaded());
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() => _shellError = error.message);
    } finally {
      if (mounted) setState(() => _loadingShell = false);
    }
  }

  Future<void> _ensureReviewLoaded({bool forceReload = false}) async {
    final question = _currentQuestion;
    if (question == null) return;
    final existing = _reviews[question.id];
    if (existing != null &&
        !forceReload &&
        !existing.loading &&
        existing.error == null &&
        existing.hasLoaded) {
      return;
    }
    final review = existing ?? QuestionReviewState();
    review.loading = true;
    review.error = null;
    setState(() => _reviews[question.id] = review);
    try {
      final recognitions = await widget.dependencies.listRecognitions(
        widget.submissionId,
        question.id,
      );
      final grades = await widget.dependencies.listGrades(
        widget.submissionId,
        question.id,
      );
      final annotations = await widget.dependencies.listAnnotations(
        widget.submissionId,
        question.id,
      );
      if (!mounted) return;
      setState(() {
        review.recognitions = recognitions;
        review.grades = grades;
        review.annotations = annotations;
        review.loading = false;
      });
    } on SidecarApiException catch (error) {
      if (!mounted) return;
      setState(() {
        review.error = error.message;
        review.loading = false;
      });
    }
  }

  void _selectQuestion(int index) {
    if (index < 0 || index >= _questions.length || index == _questionIndex) {
      return;
    }
    final previousPage = _currentQuestion?.page;
    setState(() => _questionIndex = index);
    final question = _currentQuestion!;
    _noteController.text = _reviews[question.id]?.note ?? '';
    // Only move the viewer when the target question is on a different page --
    // staying on the same page keeps whatever zoom/scroll the reviewer set
    // (Issue #21 acceptance: "Question/Submission移動、zoom/scrollを保った
    // page表示").
    if (previousPage != question.page && _pdfController.isReady) {
      unawaited(_pdfController.goToPage(pageNumber: question.page));
    }
    unawaited(_ensureReviewLoaded());
  }

  void _moveQuestion(int delta) => _selectQuestion(_questionIndex + delta);

  void _setDecision(ReviewDecision decision) {
    final question = _currentQuestion;
    if (question == null) return;
    final review = _reviews.putIfAbsent(question.id, QuestionReviewState.new);
    setState(() => review.decision = decision);
  }

  void _approveAndNext() {
    _setDecision(ReviewDecision.approved);
    if (_questionIndex < _questions.length - 1) {
      _moveQuestion(1);
    } else {
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('最後の設問です')));
    }
  }

  void _reject() => _setDecision(ReviewDecision.rejected);

  void _focusEdit() => _noteFocusNode.requestFocus();

  void _saveNote(String value) {
    final question = _currentQuestion;
    if (question == null) return;
    final review = _reviews.putIfAbsent(question.id, QuestionReviewState.new);
    review.note = value;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: Text(_appBarTitle())),
      body: _loadingShell
          ? const Center(
              key: Key('review-loading'),
              child: CircularProgressIndicator(),
            )
          : _shellError != null
          ? _buildShellError()
          : _questions.isEmpty
          ? const Center(
              key: Key('review-empty-shell'),
              child: Text('この設問構成にはまだ設問がありません'),
            )
          : CallbackShortcuts(
              bindings: {
                LogicalKeySet(LogicalKeyboardKey.arrowDown): () =>
                    _moveQuestion(1),
                LogicalKeySet(LogicalKeyboardKey.arrowUp): () =>
                    _moveQuestion(-1),
                LogicalKeySet(LogicalKeyboardKey.enter): _approveAndNext,
                LogicalKeySet(LogicalKeyboardKey.keyX): _reject,
                LogicalKeySet(LogicalKeyboardKey.keyE): _focusEdit,
              },
              child: Focus(autofocus: true, child: _buildReviewBody(context)),
            ),
    );
  }

  String _appBarTitle() {
    final label = _submission?.studentLabel ?? widget.submissionId;
    return '添削レビュー - $label';
  }

  Widget _buildShellError() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.error_outline, size: 40),
            const SizedBox(height: 8),
            Text(_shellError!, key: const Key('review-shell-error')),
            const SizedBox(height: 16),
            FilledButton(onPressed: _loadShell, child: const Text('再試行')),
          ],
        ),
      ),
    );
  }

  Widget _buildReviewBody(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // Below this width the Inspector moves under the PDF viewer instead
        // of beside it (Issue #21 acceptance: desktopの標準/狭幅表示). The
        // Navigation Rail itself always stays a vertical rail on the left --
        // it only switches to icon-only labels -- since `NavigationRail`
        // does not support a horizontal layout.
        final narrow = constraints.maxWidth < 900;
        final rail = _buildNavigationRail(narrow: narrow);
        final inspector = _buildInspector(narrow: narrow);
        final viewerAndInspector = narrow
            ? Column(
                children: [
                  Expanded(child: _buildPdfViewer()),
                  SizedBox(height: 260, child: inspector),
                ],
              )
            : Row(
                children: [
                  Expanded(child: _buildPdfViewer()),
                  SizedBox(width: 360, child: inspector),
                ],
              );
        return Column(
          children: [
            Expanded(
              child: Row(
                children: [
                  rail,
                  const VerticalDivider(width: 1),
                  Expanded(child: viewerAndInspector),
                ],
              ),
            ),
            _buildActionBar(),
          ],
        );
      },
    );
  }

  Widget _buildNavigationRail({required bool narrow}) {
    return NavigationRail(
      key: const Key('review-question-rail'),
      selectedIndex: _questionIndex,
      onDestinationSelected: _selectQuestion,
      extended: false,
      labelType: narrow
          ? NavigationRailLabelType.none
          : NavigationRailLabelType.all,
      destinations: [
        for (final question in _questions)
          NavigationRailDestination(
            icon: _questionStatusIcon(question),
            label: Text('問${question.number}'),
          ),
      ],
    );
  }

  Icon _questionStatusIcon(QuestionResponse question) {
    final review = _reviews[question.id];
    if (review == null || review.loading) {
      return const Icon(Icons.hourglass_empty);
    }
    if (review.error != null) return const Icon(Icons.error_outline);
    return switch (review.decision) {
      ReviewDecision.approved => const Icon(Icons.check_circle),
      ReviewDecision.rejected => const Icon(Icons.cancel_outlined),
      ReviewDecision.pending => const Icon(Icons.radio_button_unchecked),
    };
  }

  Widget _buildPdfViewer() {
    final bytes = _pdfBytes;
    final question = _currentQuestion;
    if (bytes == null || question == null) {
      return const SizedBox.shrink();
    }
    return Semantics(
      label: '答案PDF 問${question.number} ページ${question.page}',
      child: PdfViewer.data(
        bytes,
        sourceName: widget.submissionId,
        controller: _pdfController,
        initialPageNumber: question.page,
        params: PdfViewerParams(
          pageOverlaysBuilder: (context, pageRect, page) =>
              _buildAnnotationOverlay(page.pageNumber, pageRect.size),
        ),
      ),
    );
  }

  List<Widget> _buildAnnotationOverlay(int pageNumber, Size pageSize) {
    final widgets = <Widget>[];
    for (final question in _questions) {
      if (question.page != pageNumber) continue;
      final review = _reviews[question.id];
      if (review == null) continue;
      for (final annotation in review.placedAnnotations) {
        final rect = normalizedRectToLocal(annotation.rect!, pageSize);
        widgets.add(
          Positioned(
            key: Key('annotation-${annotation.id}'),
            left: rect.left,
            top: rect.top,
            width: rect.width,
            height: rect.height,
            child: _AnnotationMark(
              annotation: annotation,
              latestGrade: review.latestGrade,
            ),
          ),
        );
      }
    }
    return widgets;
  }

  Widget _buildInspector({required bool narrow}) {
    final question = _currentQuestion;
    final review = _currentReview;
    if (question == null) {
      return const SizedBox.shrink();
    }
    return SingleChildScrollView(
      key: const Key('review-inspector'),
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Text(
            '問${question.number}',
            style: Theme.of(context).textTheme.titleLarge,
          ),
          const SizedBox(height: 8),
          _buildSubmissionStateChip(),
          const SizedBox(height: 16),
          if (review == null || review.loading)
            const Center(
              key: Key('review-question-loading'),
              child: Padding(
                padding: EdgeInsets.all(24),
                child: CircularProgressIndicator(),
              ),
            )
          else if (review.error != null)
            _buildQuestionError(review.error!)
          else
            _buildQuestionContent(question, review),
        ],
      ),
    );
  }

  Widget _buildSubmissionStateChip() {
    final state = _submission?.state ?? 'unprocessed';
    final (icon, label) = _submissionStateVisual(state);
    return Chip(
      key: const Key('review-submission-state'),
      avatar: Icon(icon, size: 18),
      label: Text(label),
    );
  }

  Widget _buildQuestionError(String message) {
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(message, key: const Key('review-question-error')),
            TextButton(
              onPressed: () => _ensureReviewLoaded(forceReload: true),
              child: const Text('再試行'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildQuestionContent(
    QuestionResponse question,
    QuestionReviewState review,
  ) {
    final recognition = review.latestRecognition;
    final grade = review.latestGrade;
    // A question can have no AI recognition/grade yet but still carry a
    // fallback annotation (e.g. a human-entered comment) -- the empty state
    // below must not swallow that, or a comment routed to this fallback
    // area (§12.4) would silently disappear for an otherwise-unprocessed
    // question.
    final isEmpty =
        recognition == null &&
        grade == null &&
        review.fallbackAnnotations.isEmpty;
    if (isEmpty) {
      return const Text('まだAI結果がありません', key: Key('review-question-empty'));
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('AI認識文字', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 4),
        if (recognition == null)
          const Text('未認識')
        else ...[
          Text(recognition.text, key: const Key('review-recognition-text')),
          const SizedBox(height: 4),
          _ConfidenceBadge(
            key: const Key('review-recognition-confidence'),
            label: '文字認識信頼度',
            confidence: recognition.confidence.toDouble(),
          ),
        ],
        const Divider(height: 24),
        Text('採点', style: Theme.of(context).textTheme.titleSmall),
        const SizedBox(height: 4),
        if (grade == null)
          const Text('未採点')
        else ...[
          Text(
            '${grade.score.awarded} / ${grade.score.maximum} 点',
            key: const Key('review-score'),
            style: Theme.of(context).textTheme.headlineSmall,
          ),
          const SizedBox(height: 4),
          _ConfidenceBadge(
            key: const Key('review-grading-confidence'),
            label: '採点信頼度',
            confidence: grade.confidence.toDouble(),
          ),
          if (grade.rationale case final rationale?
              when rationale.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text('根拠', style: Theme.of(context).textTheme.labelLarge),
            Text(rationale, key: const Key('review-rationale')),
          ],
          if (grade.criteria.isNotEmpty) ...[
            const SizedBox(height: 8),
            Text('採点基準', style: Theme.of(context).textTheme.labelLarge),
            for (final criterion in grade.criteria)
              ListTile(
                dense: true,
                contentPadding: EdgeInsets.zero,
                leading: Icon(_criterionIcon(criterion.outcome)),
                title: Text(criterion.criterionId),
                subtitle: Text(_criterionLabel(criterion.outcome)),
              ),
          ],
        ],
        if (review.fallbackAnnotations.isNotEmpty) ...[
          const Divider(height: 24),
          Text('設問コメント', style: Theme.of(context).textTheme.titleSmall),
          for (final annotation in review.fallbackAnnotations)
            ListTile(
              key: Key('fallback-annotation-${annotation.id}'),
              dense: true,
              contentPadding: EdgeInsets.zero,
              leading: const Icon(Icons.comment_outlined),
              title: Text(annotation.comment ?? annotation.anchorText ?? ''),
            ),
        ],
        const Divider(height: 24),
        Text('修正コメント', style: Theme.of(context).textTheme.titleSmall),
        TextField(
          key: const Key('review-note-field'),
          controller: _noteController,
          focusNode: _noteFocusNode,
          maxLines: 3,
          decoration: const InputDecoration(
            hintText: 'このセッション内でのみ保持されるメモです',
            border: OutlineInputBorder(),
          ),
          onChanged: _saveNote,
        ),
      ],
    );
  }

  Widget _buildActionBar() {
    return Material(
      elevation: 4,
      child: Padding(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        // Scrolls horizontally instead of overflowing at a narrow desktop
        // width (Issue #21 acceptance: desktopの標準/狭幅表示) -- every
        // button stays reachable by keyboard focus traversal regardless.
        child: SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          reverse: true,
          child: Row(
            mainAxisAlignment: MainAxisAlignment.end,
            children: [
              OutlinedButton.icon(
                key: const Key('review-edit-button'),
                onPressed: _currentQuestion == null ? null : _focusEdit,
                icon: const Icon(Icons.edit_outlined),
                label: const Text('修正 (E)'),
              ),
              const SizedBox(width: 12),
              OutlinedButton.icon(
                key: const Key('review-reject-button'),
                onPressed: _currentQuestion == null ? null : _reject,
                icon: const Icon(Icons.close),
                label: const Text('却下 (X)'),
              ),
              const SizedBox(width: 12),
              FilledButton.icon(
                key: const Key('review-approve-button'),
                onPressed: _currentQuestion == null ? null : _approveAndNext,
                icon: const Icon(Icons.check),
                label: const Text('承認して次へ (Enter)'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

(IconData, String) _submissionStateVisual(String state) => switch (state) {
  'unprocessed' => (Icons.hourglass_empty, '未処理'),
  'ai_processing' => (Icons.autorenew, 'AI処理中'),
  'ai_processed' => (Icons.check_circle_outline, 'AI処理済み'),
  'needs_review' => (Icons.warning_amber, '要確認'),
  'reviewed' => (Icons.verified_outlined, '確認済み'),
  'exported' => (Icons.file_download_done, '出力済み'),
  'error' => (Icons.error_outline, 'エラー'),
  _ => (Icons.help_outline, state),
};

IconData _criterionIcon(String outcome) => switch (outcome) {
  'pass' => Icons.check_circle_outline,
  'partial' => Icons.remove_circle_outline,
  'fail' => Icons.cancel_outlined,
  _ => Icons.help_outline,
};

String _criterionLabel(String outcome) => switch (outcome) {
  'pass' => '合格',
  'partial' => '部分合格',
  'fail' => '不合格',
  _ => outcome,
};

/// Numeric confidence + a textual level label + a distinct icon, so
/// Recognition/Grading Confidence is never distinguished by color alone
/// (Issue #21 acceptance criteria).
class _ConfidenceBadge extends StatelessWidget {
  const _ConfidenceBadge({
    super.key,
    required this.label,
    required this.confidence,
  });

  final String label;
  final double confidence;

  @override
  Widget build(BuildContext context) {
    final level = ConfidenceLevel.of(confidence);
    final icon = switch (level) {
      ConfidenceLevel.high => Icons.check_circle,
      ConfidenceLevel.medium => Icons.info_outline,
      ConfidenceLevel.low => Icons.warning_amber,
    };
    final percent = (confidence * 100).round();
    return Semantics(
      label: '$label $percent% ${level.label}',
      // Without this, the child Text's own auto-generated semantics label
      // merges with this one (joined by a newline) instead of being
      // replaced by it, and a screen reader would announce both.
      excludeSemantics: true,
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 18),
          const SizedBox(width: 4),
          Text('$label: $percent% (${level.label})'),
        ],
      ),
    );
  }
}

/// One annotation mark drawn on the PDF overlay -- shape/text always differ
/// by kind, not just color, so the mark is legible without relying on color
/// (Issue #21 acceptance criteria).
class _AnnotationMark extends StatelessWidget {
  const _AnnotationMark({required this.annotation, required this.latestGrade});

  final AnnotationResponse annotation;
  final GradeResultResponse? latestGrade;

  @override
  Widget build(BuildContext context) {
    final content = switch (annotation.kind) {
      'circle' => const _ShapeMark(icon: Icons.panorama_fisheye, label: '○'),
      'cross' => const _ShapeMark(icon: Icons.close, label: '×'),
      'triangle' => const _ShapeMark(icon: Icons.change_history, label: '△'),
      'score' => _ShapeMark(
        icon: Icons.grade_outlined,
        label: latestGrade == null ? '―' : '${latestGrade!.score.awarded}',
      ),
      // The comment text can be long -- shown as a hover tooltip, not
      // squeezed inline next to the icon like the other kinds' short labels.
      'comment' => _ShapeMark(icon: Icons.comment, tooltip: annotation.comment),
      'underline' => const _ShapeMark(
        icon: Icons.format_underlined,
        label: '_',
      ),
      'box' => const _ShapeMark(icon: Icons.crop_square, label: '囲'),
      _ => _ShapeMark(icon: Icons.push_pin_outlined, label: annotation.kind),
    };
    return Semantics(
      label: '添削記号 ${annotation.kind} ${annotation.comment ?? ''}',
      excludeSemantics: true,
      child: content,
    );
  }
}

class _ShapeMark extends StatelessWidget {
  const _ShapeMark({required this.icon, this.label = '', this.tooltip});

  final IconData icon;
  final String label;
  final String? tooltip;

  @override
  Widget build(BuildContext context) {
    final color = Theme.of(context).colorScheme.error;
    // The icon alone already distinguishes most kinds by shape (not just
    // color); `label` additionally carries information the icon can't
    // (e.g. the actual awarded score number for `score`), so it is shown
    // alongside rather than dropped.
    final child = FittedBox(
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color),
          if (label.isNotEmpty) ...[
            const SizedBox(width: 2),
            Text(label, style: TextStyle(color: color)),
          ],
        ],
      ),
    );
    if (tooltip == null || tooltip!.isEmpty) return child;
    return Tooltip(message: tooltip!, child: child);
  }
}
