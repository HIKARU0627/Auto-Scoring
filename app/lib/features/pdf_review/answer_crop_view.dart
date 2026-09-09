import 'dart:async';
import 'dart:typed_data';

import 'package:flutter/material.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';

/// 「AIが見た画像」 -- the cropped answer area, shown to the reviewer beside
/// the score it produced (Issue #122).
///
/// **Why this is on the review screen and not the registration one.** The
/// answer-area overlay Issue #105 built already lets a person fix a box, but
/// it lives where a test is set up, and by the time a score is wrong nobody
/// is looking at it. Issue #122 measured what that costs: a detected box
/// landed on the margin, the grading AI was sent a picture of blank paper,
/// and it answered "空白なので0点" with a confidence of 0.95-1.00. The screen
/// showed `0点` and `確信度 95%`, which is indistinguishable from a correct
/// zero. The reviewer had no way in.
///
/// So the crop goes where the decision is made. Issue #85 spent five rounds
/// establishing that 判断材料 and 承認 belong on one screen; **what the AI
/// actually looked at is judgement material**, and it belongs first, above
/// the text and the score derived from it.
///
/// Kept in its own file rather than added to `pdf_review_page.dart`, which is
/// already 3,000 lines and is being split under Issue #126.
class AnswerCropView extends StatefulWidget {
  const AnswerCropView({
    super.key,
    required this.submissionId,
    required this.questionId,
    required this.getAnswerImage,
    this.isNearlyBlank = false,
  });

  final String submissionId;
  final String questionId;
  final GetAnswerImage getAnswerImage;

  /// Whether intake flagged this crop as holding almost no ink
  /// (`crop_nearly_blank`, `domain.submission_intake.is_nearly_blank_crop`).
  ///
  /// The sidecar decides this, not the widget: it measures the crop's ink
  /// coverage against a threshold set from real material, and re-deriving
  /// that here from a decoded thumbnail would be a second, differently-wrong
  /// answer to the same question.
  final bool isNearlyBlank;

  @override
  State<AnswerCropView> createState() => _AnswerCropViewState();
}

class _AnswerCropViewState extends State<AnswerCropView> {
  Uint8List? _bytes;
  String? _error;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    unawaited(_load());
  }

  @override
  void didUpdateWidget(AnswerCropView oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.submissionId != widget.submissionId ||
        oldWidget.questionId != widget.questionId) {
      unawaited(_load());
    }
  }

  Future<void> _load() async {
    final submissionId = widget.submissionId;
    final questionId = widget.questionId;
    if (mounted) {
      setState(() {
        _loading = true;
        _error = null;
        _bytes = null;
      });
    }
    try {
      final bytes = await widget.getAnswerImage(submissionId, questionId);
      // The reviewer can move to another question while this is in flight;
      // a late response must not paint one question's crop under another's
      // score, which is the exact confusion this widget exists to prevent.
      if (!mounted ||
          submissionId != widget.submissionId ||
          questionId != widget.questionId) {
        return;
      }
      setState(() {
        _bytes = bytes;
        _loading = false;
      });
    } on SidecarApiException catch (error) {
      if (!mounted ||
          submissionId != widget.submissionId ||
          questionId != widget.questionId) {
        return;
      }
      setState(() {
        _error = error.statusCode == 404
            ? 'この設問の切り出し画像は記録されていません。'
            : '切り出し画像を読み込めませんでした。';
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('AIが見た画像', style: context.texts.titleSmall),
        const SizedBox(height: AppSpacing.xs),
        if (widget.isNearlyBlank) ...[
          _NearlyBlankNotice(key: const Key('review-answer-crop-blank-notice')),
          const SizedBox(height: AppSpacing.xs),
        ],
        _buildImage(context),
      ],
    );
  }

  Widget _buildImage(BuildContext context) {
    if (_loading) {
      return const Padding(
        key: Key('review-answer-crop-loading'),
        padding: EdgeInsets.symmetric(vertical: AppSpacing.sm),
        child: SizedBox(
          height: AppIconSize.standard,
          width: AppIconSize.standard,
          child: CircularProgressIndicator(strokeWidth: 2),
        ),
      );
    }
    final error = _error;
    if (error != null) {
      return Text(
        error,
        key: const Key('review-answer-crop-error'),
        style: context.texts.bodySmall?.copyWith(
          color: context.colors.onSurfaceVariant,
        ),
      );
    }
    final bytes = _bytes;
    if (bytes == null) {
      return const SizedBox.shrink();
    }
    return DecoratedBox(
      decoration: BoxDecoration(
        border: Border.all(color: context.colors.outlineVariant),
        borderRadius: AppRadius.smAll,
      ),
      child: ClipRRect(
        borderRadius: AppRadius.smAll,
        child: ConstrainedBox(
          // Bounded so a tall vertical-writing column cannot push the score
          // and the 承認 button off the panel -- the reviewer has to be able
          // to see the crop *and* the decision at once (Issue #85).
          constraints: const BoxConstraints(maxHeight: _maxCropHeight),
          child: Image.memory(
            bytes,
            key: const Key('review-answer-crop-image'),
            fit: BoxFit.contain,
            // A crop is a scan of handwriting; smoothing it makes faint
            // strokes harder to judge, not easier.
            filterQuality: FilterQuality.none,
            errorBuilder: (context, error, stack) => Text(
              '切り出し画像を表示できませんでした。',
              key: const Key('review-answer-crop-undecodable'),
              style: context.texts.bodySmall,
            ),
          ),
        ),
      ),
    );
  }
}

const double _maxCropHeight = 220;

/// Says the crop is as good as blank, and -- deliberately -- does not say
/// which of the two reasons it is.
///
/// Nothing can tell "the answer area is in the wrong place" from "the student
/// left it blank" by looking at the crop, and Issue #122 measured that a
/// threshold raised until it could would start rejecting real answers. So the
/// notice names both and asks the person to look, rather than asserting the
/// one that happens to be more common.
class _NearlyBlankNotice extends StatelessWidget {
  const _NearlyBlankNotice({super.key});

  @override
  Widget build(BuildContext context) {
    final tone = AppStatusTone.attention.color(context);
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(
          Icons.warning_amber_outlined,
          size: AppIconSize.dense,
          color: tone,
        ),
        const SizedBox(width: AppSpacing.xs),
        Expanded(
          child: Text(
            'この切り出しにはほとんど何も写っていません。'
            '回答欄の位置がずれているか、答案が無記入です。',
            style: context.texts.bodySmall?.copyWith(color: tone),
          ),
        ),
      ],
    );
  }
}
