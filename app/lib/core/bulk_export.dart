/// テスト単位の一括PDF出力 (Issue #142) -- 対象の決め方と、出し切るまでの進行。
///
/// **ウィジェットを持たない。** `review_queue.dart` や `home_dashboard.dart` と
/// 同じ理由で、「どれが対象か」「途中で何が起きたか」は画面を立ち上げずに
/// `bulk_export_test.dart` から直接読めなければならない。40枚を流している最中の
/// 挙動こそ、この機能で一番意見の入るところである。
///
/// 進め方は `docs/pdf-export.md` §12 の決定に従う:
///
/// * 対象は**テスト単位**。既定は「全設問が確定した答案すべて」で、対象外は
///   理由付きで数えて見せる ([BulkExportPlan])。
/// * 出力先フォルダは**1回だけ**選び、答案ごとに1ファイルへ分ける。
/// * **途中で止めない。** 1枚の失敗で残りを落とさない ([BulkExportRunner])。
/// * 「n / 全件」と、いま出している答案が見えること。中止できること。
library;

import 'dart:typed_data';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/review_queue.dart';

/// 一括出力に出す答案1件。[label] は画面に出す名前で、答案キューの行と
/// **同じ規則**で選ぶ (`submission_queue_page.dart`) -- 一覧とダイアログで
/// 違う名前が出たら、講師はどの答案の話をされているのか分からなくなる。
class BulkExportTarget {
  const BulkExportTarget({required this.submissionId, required this.label});

  final String submissionId;
  final String label;
}

/// 対象外の答案1件と、**なぜ外れたか**。
///
/// 数だけ出して理由を伏せると、「40枚あるのに37枚しか出ない」を講師が
/// 自分で調べる羽目になる。
class BulkExportExclusion {
  const BulkExportExclusion({
    required this.submissionId,
    required this.label,
    required this.reason,
  });

  final String submissionId;
  final String label;
  final String reason;
}

/// 実行前に人が見て確認するもの -- 対象と、対象外とその理由。
class BulkExportPlan {
  const BulkExportPlan({required this.targets, required this.excluded});

  /// 答案キューの並び ([ReviewQueue.entries]) をそのまま引き継ぐ。
  ///
  /// **対象の判定は `ReviewQueueEntry.isFullyConfirmed` を使い回す。** 行ごとの
  /// 「PDF出力」ボタンを出す条件 (Issue #137) と同じ述語で、その先はサイドカーの
  /// `domain.pdf_export.export_refusal` と同じ数を読んでいる。ここで3つ目の
  /// 数え方を作ると、一覧・単発出力・一括出力が三者三様に食い違う。
  ///
  /// **ここでの判定は「見込み」であって、可否を決めるのはサイドカーである。**
  /// 点数を書く場所が無い ([ExportRefusalReason.noRoomForScore]) は答案の
  /// 進捗からは分からないので、それは実行中の失敗として現れる。
  factory BulkExportPlan.from(ReviewQueue queue) {
    final targets = <BulkExportTarget>[];
    final excluded = <BulkExportExclusion>[];
    for (final entry in queue.entries) {
      final label = bulkExportLabel(entry.submission);
      if (entry.isFullyConfirmed) {
        targets.add(BulkExportTarget(submissionId: entry.id, label: label));
        continue;
      }
      excluded.add(
        BulkExportExclusion(
          submissionId: entry.id,
          label: label,
          reason: entry.totalQuestions == 0
              // 進捗が引けなかったときもここへ来る。「設問が0問」と
              // 「進捗が取れていない」を見分ける材料がこちらに無いので、
              // 分からないとは言うが、確定済みだとは言わない。
              ? '設問ごとの確定状況が取れていません'
              : '未確認の設問が'
                    '${entry.totalQuestions - entry.confirmedQuestions}問あります',
        ),
      );
    }
    return BulkExportPlan(targets: targets, excluded: excluded);
  }

  final List<BulkExportTarget> targets;
  final List<BulkExportExclusion> excluded;

  bool get hasTargets => targets.isNotEmpty;
}

/// 答案キューの行と同じ表示名。
String bulkExportLabel(SubmissionResponse submission) =>
    submission.studentLabel ?? submission.originalFilename ?? submission.id;

/// 答案1件の、一括出力での行き先。
enum BulkExportItemState {
  /// まだ出ていない (キュー待ち・出力中)。
  pending,

  /// 出力先フォルダへ書けた。
  written,

  /// 出せなかった。[BulkExportItemResult.failureReason] に理由がある。
  failed,

  /// 中止されて、着手されないまま終わった。**失敗とは別に数える** --
  /// 講師が自分で止めたものを「失敗3件」と報告されるのは嘘である。
  cancelled,
}

/// 答案1件の結果。
class BulkExportItemResult {
  const BulkExportItemResult({
    required this.target,
    required this.state,
    this.savedPath,
    this.failureReason,
  });

  final BulkExportTarget target;
  final BulkExportItemState state;

  /// 実際に書いた絶対パス ([BulkExportItemState.written] のときだけ)。
  final String? savedPath;

  /// 出せなかった理由 ([BulkExportItemState.failed] のときだけ)。
  final String? failureReason;

  BulkExportItemResult _withOutcome(
    BulkExportItemState state, {
    String? savedPath,
    String? failureReason,
  }) => BulkExportItemResult(
    target: target,
    state: state,
    savedPath: savedPath,
    failureReason: failureReason,
  );
}

/// 実行中の見え方 -- 「n / 全件」と、いま出している答案。
///
/// **無音で止まって見える状態を作らないため**にこれがある (Issue #142)。
class BulkExportProgress {
  const BulkExportProgress({required this.items, required this.currentLabel});

  final List<BulkExportItemResult> items;

  /// いま出している答案の表示名。**まだ終わっていないもののうち先頭**を出す。
  /// サイドカーのキューは並列に走りうるので、これは「止まっていない証拠」で
  /// あって「これ1枚だけを処理中」という意味ではない。
  final String? currentLabel;

  int get totalCount => items.length;

  /// 出し終わった数 = 書けた + 失敗 + 中止。**「書けた数」ではない** --
  /// 進捗が失敗で止まったように見えるのを避ける。
  int get settledCount =>
      items.where((item) => item.state != BulkExportItemState.pending).length;

  int get writtenCount =>
      items.where((item) => item.state == BulkExportItemState.written).length;

  List<BulkExportItemResult> get failures =>
      items.where((item) => item.state == BulkExportItemState.failed).toList();

  List<BulkExportItemResult> get cancelled => items
      .where((item) => item.state == BulkExportItemState.cancelled)
      .toList();

  /// もう一度試す価値のあるもの -- 失敗と、中止されて着手されなかったもの。
  List<BulkExportTarget> get retryableTargets => items
      .where(
        (item) =>
            item.state == BulkExportItemState.failed ||
            item.state == BulkExportItemState.cancelled,
      )
      .map((item) => item.target)
      .toList();
}

/// 出力先フォルダへ1ファイル書き、実際に書いたパスを返す。
///
/// 注入できるようにしてあるのは、ウィジェットテストに本物のフォルダを
/// 掘らせないためである。実装は `bulk_export_writer.dart`。
typedef BulkExportFileWriter =
    Future<String> Function(String directory, String fileName, Uint8List bytes);

/// 答案1件の結末を記録し、進捗を1つ進める ([BulkExportRunner.run] の内側)。
typedef _Settle =
    void Function(
      String submissionId,
      BulkExportItemState state, {
      String? savedPath,
      String? failureReason,
    });

/// サイドカーが断った理由を、一覧の1行に収まる日本語にする。
///
/// 文言は `core/widgets/export_dialog.dart` の単発出力と揃えてある
/// (**同じ拒否を2画面が別の言葉で説明しない**)。知らないコードが来たら
/// 推測せず、そう言う -- 嘘の理由より、そっけない理由のほうがましである。
String bulkExportRefusalReason(BulkExportItemResponse item) {
  final questions = item.refusalQuestionIds?.toList() ?? const <String>[];
  switch (item.refusalCode) {
    case ExportRefusalReason.unconfirmedQuestions:
      return '未確認の設問が${questions.length}問あります';
    case ExportRefusalReason.noRoomForScore:
      // 確定させても解消しない。Issue #150 で実際に起きたとおり、これを
      // 言わないと講師は済んでいる確定作業を繰り返す。
      return '点数を書き込める場所がありません (確定操作では解消しません)';
    default:
      return 'サイドカーが出力を断りました';
  }
}

/// 一括出力を、最後まで走らせる。
///
/// **1枚の失敗で止めない。** サイドカーの `POST /tests/{id}/export` は答案ごとの
/// 行を返す (拒否は例外ではなく行) ので、こちらも行ごとに畳んでいく。ジョブの
/// 失敗・取得失敗・書き込み失敗も同じ扱いで、その1件だけを失敗にして次へ進む。
///
/// ジョブは**まとめて積んでから**待つ。1件ずつ「投げて待って次」にすると、
/// サイドカーのキューの並列度が丸ごと遊ぶうえ、pollの間隔が枚数分そのまま
/// 待ち時間になる (`docs/pdf-export.md` §12.3)。
class BulkExportRunner {
  BulkExportRunner({
    required AppDependencies dependencies,
    required BulkExportFileWriter writeFile,
    this.pollInterval = const Duration(milliseconds: 500),

    /// 進捗の取得が transport で失敗し続けたときに、その答案を失敗と
    /// 認めるまでの回数。単発出力 (`export_dialog.dart`) と同じ考え方で、
    /// 一度の瞬断でジョブを失敗扱いにしない。
    this.maxTransientPollFailures = 5,
  }) : _dependencies = dependencies,
       _writeFile = writeFile;

  final AppDependencies _dependencies;
  final BulkExportFileWriter _writeFile;
  final Duration pollInterval;
  final int maxTransientPollFailures;

  bool _cancelled = false;

  /// 中止を要求する。走っている [run] は、いま書いている1件を書き終えてから
  /// 止まり、まだ始まっていないジョブをサイドカー側でも取り消す。
  void cancel() => _cancelled = true;

  Future<BulkExportProgress> run({
    required String testId,
    required List<BulkExportTarget> targets,
    required String destinationDirectory,
    void Function(BulkExportProgress progress)? onProgress,
  }) async {
    _cancelled = false;
    final results = <String, BulkExportItemResult>{
      for (final target in targets)
        target.submissionId: BulkExportItemResult(
          target: target,
          state: BulkExportItemState.pending,
        ),
    };
    final order = [for (final target in targets) target.submissionId];

    void emit() {
      final items = [for (final id in order) results[id]!];
      onProgress?.call(
        BulkExportProgress(
          items: items,
          currentLabel: items
              .where((item) => item.state == BulkExportItemState.pending)
              .map((item) => item.target.label)
              .firstOrNull,
        ),
      );
    }

    /// 最後の1回。**いま出している答案はもう無い**ので `currentLabel` は
    /// 空になり、これがそのまま [run] の戻り値になる。
    BulkExportProgress finish() {
      final progress = BulkExportProgress(
        items: [for (final id in order) results[id]!],
        currentLabel: null,
      );
      onProgress?.call(progress);
      return progress;
    }

    void settle(
      String submissionId,
      BulkExportItemState state, {
      String? savedPath,
      String? failureReason,
    }) {
      results[submissionId] = results[submissionId]!._withOutcome(
        state,
        savedPath: savedPath,
        failureReason: failureReason,
      );
      emit();
    }

    emit();
    if (targets.isEmpty) return finish();

    final BulkExportResponse response;
    try {
      response = await _dependencies.requestBulkExport(
        testId,
        submissionIds: order,
      );
    } on SidecarApiException catch (error) {
      // 1件も始まっていない。全件を同じ理由で失敗にする -- 黙って空の
      // 結果を返すと「対象が0件だった」と読めてしまう。
      for (final submissionId in order) {
        settle(
          submissionId,
          BulkExportItemState.failed,
          failureReason: error.message,
        );
      }
      return finish();
    }

    final pendingJobs = <String, String>{};
    final readyExports = <String, ExportResponse>{};
    for (final item in response.items) {
      if (!results.containsKey(item.submissionId)) continue;
      switch (item.status) {
        case BulkExportItemStatus.refused:
          settle(
            item.submissionId,
            BulkExportItemState.failed,
            failureReason: bulkExportRefusalReason(item),
          );
        case BulkExportItemStatus.reused:
          final export = item.export_;
          if (export == null) {
            settle(
              item.submissionId,
              BulkExportItemState.failed,
              failureReason: 'sidecar は出力済みファイルを返しませんでした',
            );
          } else {
            readyExports[item.submissionId] = export;
          }
        case BulkExportItemStatus.queued:
          final jobId = item.jobId;
          if (jobId == null) {
            settle(
              item.submissionId,
              BulkExportItemState.failed,
              failureReason: 'sidecar は job_id を返しませんでした',
            );
          } else {
            pendingJobs[item.submissionId] = jobId;
          }
        default:
          settle(
            item.submissionId,
            BulkExportItemState.failed,
            failureReason: 'sidecar が知らない状態を返しました: ${item.status}',
          );
      }
    }
    // 応答に現れなかった答案。数が合わないまま成功と report しない。
    for (final submissionId in order) {
      if (results[submissionId]!.state == BulkExportItemState.pending &&
          !pendingJobs.containsKey(submissionId) &&
          !readyExports.containsKey(submissionId)) {
        settle(
          submissionId,
          BulkExportItemState.failed,
          failureReason: 'sidecar の応答にこの答案が含まれていませんでした',
        );
      }
    }

    for (final submissionId in order) {
      if (_cancelled) break;
      final export = readyExports[submissionId];
      if (export == null) continue;
      await _writeExport(
        submissionId: submissionId,
        exportId: export.id,
        fileName: bulkExportFileName(export.filePath),
        destinationDirectory: destinationDirectory,
        settle: settle,
      );
    }

    final transientFailures = <String, int>{};
    while (pendingJobs.isNotEmpty && !_cancelled) {
      await Future<void>.delayed(pollInterval);
      for (final submissionId in List<String>.from(order)) {
        if (_cancelled) break;
        final jobId = pendingJobs[submissionId];
        if (jobId == null) continue;
        final JobResponse job;
        try {
          job = await _dependencies.getJob(jobId);
        } on SidecarApiException catch (error) {
          final failures = (transientFailures[submissionId] ?? 0) + 1;
          transientFailures[submissionId] = failures;
          if (failures >= maxTransientPollFailures) {
            pendingJobs.remove(submissionId);
            settle(
              submissionId,
              BulkExportItemState.failed,
              failureReason: '進捗の取得に失敗しました: ${error.message}',
            );
          }
          continue;
        }
        transientFailures[submissionId] = 0;
        switch (job.state) {
          case 'succeeded':
            pendingJobs.remove(submissionId);
            await _writeExportForJob(
              submissionId: submissionId,
              jobId: jobId,
              destinationDirectory: destinationDirectory,
              settle: settle,
            );
          case 'failed':
            pendingJobs.remove(submissionId);
            settle(
              submissionId,
              BulkExportItemState.failed,
              failureReason: job.lastError ?? '出力に失敗しました',
            );
          case 'cancelled':
            pendingJobs.remove(submissionId);
            settle(
              submissionId,
              BulkExportItemState.cancelled,
              failureReason: '出力が取り消されました',
            );
        }
      }
    }

    if (_cancelled) {
      // 見るのをやめるだけでは中止にならない。まだ始まっていないジョブを
      // サイドカー側でも取り消さないと、誰も要らなくなったPDFを機械が
      // 作り続ける。取り消しそのものの失敗は握りつぶす -- すでに終わって
      // いたなら取り消す必要は無いし、講師にできることも無い。
      for (final entry in pendingJobs.entries) {
        try {
          await _dependencies.cancelJob(entry.value);
        } on SidecarApiException {
          // 取り消せなかった: そのジョブはもう終わっているか、届かない。
        }
        settle(entry.key, BulkExportItemState.cancelled);
      }
      for (final submissionId in order) {
        if (results[submissionId]!.state == BulkExportItemState.pending) {
          settle(submissionId, BulkExportItemState.cancelled);
        }
      }
    }

    return finish();
  }

  Future<void> _writeExportForJob({
    required String submissionId,
    required String jobId,
    required String destinationDirectory,
    required _Settle settle,
  }) async {
    final ExportResponse export;
    try {
      final exports = await _dependencies.listExports(submissionId);
      final matching = exports.where((export) => export.jobId == jobId);
      if (matching.isEmpty) {
        settle(
          submissionId,
          BulkExportItemState.failed,
          failureReason: '出力は終わりましたが、生成されたファイルが見つかりません',
        );
        return;
      }
      export = matching.last;
    } on SidecarApiException catch (error) {
      settle(
        submissionId,
        BulkExportItemState.failed,
        failureReason: '出力結果の取得に失敗しました: ${error.message}',
      );
      return;
    }
    await _writeExport(
      submissionId: submissionId,
      exportId: export.id,
      fileName: bulkExportFileName(export.filePath),
      destinationDirectory: destinationDirectory,
      settle: settle,
    );
  }

  Future<void> _writeExport({
    required String submissionId,
    required String exportId,
    required String fileName,
    required String destinationDirectory,
    required _Settle settle,
  }) async {
    try {
      final bytes = await _dependencies.getExportFile(exportId);
      final savedPath = await _writeFile(destinationDirectory, fileName, bytes);
      settle(submissionId, BulkExportItemState.written, savedPath: savedPath);
    } on SidecarApiException catch (error) {
      settle(
        submissionId,
        BulkExportItemState.failed,
        failureReason: 'ファイルの取得に失敗しました: ${error.message}',
      );
    } on Exception catch (error) {
      // 書き込み側 (権限が無い、USBが抜けた、容量が足りない) の失敗。
      // ここで投げると残りの答案まで道連れになる。
      settle(
        submissionId,
        BulkExportItemState.failed,
        failureReason: 'ファイルを書き込めませんでした: $error',
      );
    }
  }
}

/// 出力先へ置くファイル名 = サイドカーが `app-data/exports/` に付けた名前。
///
/// **命名規則を作り直さない** (Issue #142)。単発出力が既に
/// `<元のファイル名>_corrected[_N].pdf` を決めており
/// (`LocalFileStore.allocate_export_path`)、その名前は画面が「保存先」として
/// 見せてきたものでもある。ここで別の名前を付けると、同じ添削PDFが場所に
/// よって違う名前で存在することになる。
String bulkExportFileName(String exportFilePath) =>
    exportFilePath.split('/').last;
