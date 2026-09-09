import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/design/app_status_tone.dart';
import 'package:auto_scoring_app/core/design/app_theme_context.dart';
import 'package:auto_scoring_app/core/design/design_tokens.dart';
import 'package:auto_scoring_app/core/review_queue.dart';
import 'package:auto_scoring_app/core/submission_review_reason.dart';
import 'package:auto_scoring_app/core/submission_status.dart';

/// 答案キュー画面 (Issue #113)。
///
/// 1つのテストの答案が**何枚あって、どれが済んでいて、次はどれか**を出す。
/// これが無かったので、40枚を続けてさばくには1枚ごとにホームへ戻るしかなかった。
///
/// **済んだ答案も隠さない。** 絞り込んで見せないのは、残りの中身を読み分ける
/// 手がかりごと消すことになる (`docs/review-queue.md`)。代わりに、状態は行の中で
/// 分かるようにしてある。
class SubmissionQueuePage extends ConsumerStatefulWidget {
  const SubmissionQueuePage({required this.testId, super.key});

  final String testId;

  @override
  ConsumerState<SubmissionQueuePage> createState() =>
      _SubmissionQueuePageState();
}

/// 一度の読み込みで揃うもの。3本の要求をまとめて待つのは、**どれか1つが欠けた
/// 中途半端な一覧を出さないため**である。
class _QueueData {
  const _QueueData({required this.test, required this.queue});

  final TestResponse test;
  final ReviewQueue queue;
}

class _SubmissionQueuePageState extends ConsumerState<SubmissionQueuePage> {
  /// The sidecar operations this screen was opened against, captured once in
  /// [initState] -- never re-resolved from the provider mid-request. See
  /// [appDependenciesProvider] for why that rule exists.
  late final AppDependencies _dependencies;

  late Future<_QueueData> _dataFuture;

  @override
  void initState() {
    super.initState();
    _dependencies = ref.read(appDependenciesProvider);
    _dataFuture = _load();
  }

  Future<_QueueData> _load() async {
    final test = await _dependencies.getTest(widget.testId);
    final submissions = await _dependencies.listSubmissions(widget.testId);
    // 進捗だけは落ちても続ける。数が出ないのは、一覧が出ないより軽い --
    // 「3 / 5」が消えるだけで、どの答案がどの状態かは `state` から描ける。
    var progress = const <SubmissionReviewProgressResponse>[];
    try {
      progress = await _dependencies.listReviewProgress(widget.testId);
    } on SidecarApiException {
      progress = const [];
    }
    return _QueueData(
      test: test,
      queue: ReviewQueue.from(submissions: submissions, progress: progress),
    );
  }

  Future<void> _reload() async {
    final future = _load();
    // A block body, not an arrow: an assignment expression evaluates to the
    // assigned value, so an arrow body would hand `setState` a closure that
    // returns the `Future` itself, which Flutter rejects at runtime.
    setState(() {
      _dataFuture = future;
    });
    try {
      await future;
    } catch (_) {
      // `_dataFuture` already carries this to the `FutureBuilder`, which
      // renders it as `snapshot.hasError`. Swallowed here so a recoverable
      // sidecar failure during a refresh does not *also* surface as an
      // unhandled async error from `RefreshIndicator.onRefresh`.
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('答案キュー')),
      body: FutureBuilder<_QueueData>(
        future: _dataFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState != ConnectionState.done) {
            return const Center(child: CircularProgressIndicator());
          }
          if (snapshot.hasError) {
            final error = snapshot.error;
            final message = error is SidecarApiException
                ? error.message
                : '$error';
            return _MessageBody(
              key: const Key('queue-error'),
              icon: Icons.error_outline,
              tone: AppStatusTone.danger,
              message: '答案の一覧を取得できません: $message',
              onRetry: _reload,
            );
          }
          final data = snapshot.data!;
          if (data.queue.isEmpty) {
            return _MessageBody(
              key: const Key('queue-empty'),
              icon: Icons.inbox_outlined,
              tone: AppStatusTone.neutral,
              message: 'このテストにはまだ答案が取り込まれていません。',
              onRetry: _reload,
            );
          }
          return RefreshIndicator(
            onRefresh: _reload,
            child: Column(
              children: [
                _QueueHeader(test: data.test, queue: data.queue),
                const Divider(height: AppLayout.hairline),
                Expanded(
                  child: ListView.separated(
                    itemCount: data.queue.total,
                    separatorBuilder: (_, _) =>
                        const Divider(height: AppLayout.hairline),
                    itemBuilder: (context, index) => _QueueRow(
                      entry: data.queue.entries[index],
                      position: index + 1,
                      total: data.queue.total,
                      onOpen: () async {
                        await context.push(
                          AppRoutes.pdfReview(
                            testId: widget.testId,
                            submissionId: data.queue.entries[index].id,
                          ),
                        );
                        // 戻ってきたときには、その答案が済んでいるかもしれない。
                        if (mounted) await _reload();
                      },
                    ),
                  ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }
}

/// テスト名と「確認済み N / M」。ホームのカードと同じ語彙にしてある。
class _QueueHeader extends StatelessWidget {
  const _QueueHeader({required this.test, required this.queue});

  final TestResponse test;
  final ReviewQueue queue;

  @override
  Widget build(BuildContext context) {
    final done = queue.doneCount;
    return Padding(
      padding: AppSpacing.card,
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // ホームのテストカードと同じ役割・同じ語彙で出す。同じ数を2画面が
          // 違う顔で見せると、どちらが本当か分からなくなる。
          Text(test.name, style: context.texts.titleMedium),
          const SizedBox(height: AppSpacing.sm),
          Text('確認済み $done / ${queue.total}', style: context.texts.bodyMedium),
          const SizedBox(height: AppSpacing.xs),
          LinearProgressIndicator(
            value: queue.total == 0 ? 0 : done / queue.total,
            borderRadius: AppRadius.smAll,
            semanticsLabel: '${test.name} の確認済み答案',
          ),
        ],
      ),
    );
  }
}

/// 答案1件の行。
///
/// 状態は [SubmissionStatusVisual] から取る。**この画面が3つ目の対応表を作っては
/// ならない** -- 同じ `ai_processed` を一方が「処理済み」他方が「AI処理済み」と
/// 呼んでいたのが Issue #84 の小さい方の版である。
class _QueueRow extends StatelessWidget {
  const _QueueRow({
    required this.entry,
    required this.position,
    required this.total,
    required this.onOpen,
  });

  final ReviewQueueEntry entry;
  final int position;
  final int total;
  final VoidCallback onOpen;

  String? get _reasonSummary =>
      describeReviewReason(entry.submission.reviewReason);

  @override
  Widget build(BuildContext context) {
    final visual = SubmissionStatusVisual.of(entry.submission.state);
    return ListTile(
      key: Key('queue-row-${entry.id}'),
      leading: Icon(visual.icon, color: visual.tone.color(context)),
      title: Text(_answerName(entry.submission)),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const SizedBox(height: AppSpacing.xs),
          Wrap(
            spacing: AppSpacing.md,
            runSpacing: AppSpacing.xs,
            crossAxisAlignment: WrapCrossAlignment.center,
            children: [
              Text('$position / $total', style: context.textRoles.uiLabel),
              Text(visual.label, style: context.textRoles.uiLabel),
              if (entry.totalQuestions > 0) _ProgressChip(entry: entry),
              // この答案だけは、AIの提案を確認するのではなく**自分で点数を
              // 入れる**必要がある (Issue #118 の「点数を入力」)。残り3枚が
              // 「見るだけ」なのか「1問ずつ採点する」なのかで、残り時間の
              // 見積もりがまるで違う。
              //
              // 文言は添削レビュー画面の `review-ai-grading-failed` と同じ語に
              // 揃えてある -- 一覧で読んだことと、開いた先で読むことが別の言葉に
              // なってはいけない (Issue #84)。
              if (entry.needsManualGrading)
                _Marker(
                  key: Key('queue-manual-grade-${entry.id}'),
                  icon: Icons.edit_note,
                  tone: AppStatusTone.attention,
                  label: 'AIが採点できなかった設問があります',
                ),
            ],
          ),
          // **生の `review_reason` は出さない。** あれは
          // `answer_area_undefined:q-1;crop_nearly_blank:q-2,q-3` という
          // ワイヤ形式で、講師に読ませるものではない (Issue #122 が
          // `core/submission_review_reason.dart` を置いた理由そのもの)。
          // 知らない旗しか無ければ何も出さない -- 状態ラベルだけで足りる。
          if (_reasonSummary case final summary?) ...[
            const SizedBox(height: AppSpacing.xs),
            Text(summary, style: context.textRoles.uiLabel),
          ],
        ],
      ),
      isThreeLine: _reasonSummary != null,
      onTap: onOpen,
    );
  }
}

/// 「3 / 5 問 確定」。
///
/// **これが無いと、途中まで確定した答案が手つかずと同じ見た目になる。** 答案の
/// 状態が動くのは全設問が確定したときだけ (Issue #112) なので、中断して戻って
/// きた講師には「どこまでやったか」が読めない。
class _ProgressChip extends StatelessWidget {
  const _ProgressChip({required this.entry});

  final ReviewQueueEntry entry;

  @override
  Widget build(BuildContext context) {
    final tone = entry.isDone
        ? AppStatusTone.success
        : entry.isPartiallyReviewed
        ? AppStatusTone.attention
        : AppStatusTone.neutral;
    return _Marker(
      key: Key('queue-progress-${entry.id}'),
      icon: entry.isPartiallyReviewed ? Icons.timelapse : Icons.checklist_rtl,
      tone: tone,
      label: '${entry.confirmedQuestions} / ${entry.totalQuestions} 問 確定',
    );
  }
}

/// アイコン＋ラベルの小さな並び。色は状態の唯一の手がかりにしない (Issue #25)。
class _Marker extends StatelessWidget {
  const _Marker({
    required this.icon,
    required this.tone,
    required this.label,
    super.key,
  });

  final IconData icon;
  final AppStatusTone tone;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: AppIconSize.inline, color: tone.color(context)),
        const SizedBox(width: AppSpacing.xs),
        Text(label, style: context.textRoles.uiLabel),
      ],
    );
  }
}

class _MessageBody extends StatelessWidget {
  const _MessageBody({
    required this.icon,
    required this.tone,
    required this.message,
    required this.onRetry,
    super.key,
  });

  final IconData icon;
  final AppStatusTone tone;
  final String message;
  final Future<void> Function() onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: AppSpacing.page,
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: AppIconSize.display, color: tone.color(context)),
            const SizedBox(height: AppSpacing.lg),
            Text(message, textAlign: TextAlign.center),
            const SizedBox(height: AppSpacing.lg),
            OutlinedButton.icon(
              onPressed: () => onRetry(),
              icon: const Icon(Icons.refresh),
              label: const Text('再読み込み'),
            ),
          ],
        ),
      ),
    );
  }
}

/// 行の見出しに出す答案の呼び名。
///
/// `student_label` -> 元のファイル名 -> id の順。**id まで落ちても何かは出す** --
/// 名前が無い答案が一覧から消えたように見えるのが一番困る。
String _answerName(SubmissionResponse submission) =>
    submission.studentLabel ?? submission.originalFilename ?? submission.id;
