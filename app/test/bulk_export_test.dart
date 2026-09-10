import 'dart:io';
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_theme.dart';
import 'package:auto_scoring_app/core/bulk_export.dart';
import 'package:auto_scoring_app/core/review_queue.dart';
import 'package:auto_scoring_app/core/widgets/bulk_export_dialog.dart';

import 'app_harness.dart';

/// 一括PDF出力 (Issue #142)。
///
/// 通しで見ているのは **対象一覧の確認 → 出力先選択 → 進捗 → 失敗一覧** の
/// 一本道で、途中の1件が転んでも残りが出ることを毎回確かめている。
/// 「対象が0件のとき何が出るか」も同じくらい大事なので独立に見ている --
/// そこで黙って何も起きないのが、この機能で一番ありそうな行き止まりである。

SubmissionResponse _submission({
  required String id,
  String? label,
  int day = 1,
}) => SubmissionResponse(
  (b) => b
    ..id = id
    ..testId = 'test-1'
    ..state = 'ai_processed'
    ..pageCount = 1
    ..studentLabel = label
    ..createdAt = DateTime.utc(2026, 2, day),
);

SubmissionReviewProgressResponse _progress({
  required String id,
  int total = 2,
  int confirmed = 2,
}) => SubmissionReviewProgressResponse(
  (b) => b
    ..submissionId = id
    ..totalQuestions = total
    ..confirmedQuestions = confirmed
    ..manualGradingQuestions = 0,
);

BulkExportItemResponse _item({
  required String submissionId,
  required BulkExportItemStatus status,
  String? jobId,
  ExportResponse? export,
  ExportRefusalReason? refusalCode,
  List<String> refusalQuestionIds = const [],
}) => BulkExportItemResponse(
  (b) => b
    ..submissionId = submissionId
    ..status = status
    ..jobId = jobId
    ..export_ = export?.toBuilder()
    ..refusalCode = refusalCode
    ..refusalQuestionIds.replace(refusalQuestionIds),
);

BulkExportResponse _response(List<BulkExportItemResponse> items) =>
    BulkExportResponse(
      (b) => b
        ..testId = 'test-1'
        ..items.replace(items),
    );

JobResponse _job({
  required String id,
  required String state,
  String? lastError,
}) => JobResponse(
  (b) => b
    ..id = id
    ..kind = 'export'
    ..submissionId = 'sub-1'
    ..state = state
    ..attempts = 0
    ..maxAttempts = 3
    ..lastError = lastError
    ..createdAt = DateTime.utc(2026, 1, 1)
    ..updatedAt = DateTime.utc(2026, 1, 1),
);

ExportResponse _export({
  required String id,
  required String submissionId,
  required String jobId,
  required String filePath,
}) => ExportResponse(
  (b) => b
    ..id = id
    ..submissionId = submissionId
    ..jobId = jobId
    ..filePath = filePath
    ..fileSha256 = 'a' * 64
    ..createdAt = DateTime.utc(2026, 1, 1),
);

ReviewQueue _queue({
  required List<SubmissionResponse> submissions,
  required List<SubmissionReviewProgressResponse> progress,
}) => ReviewQueue.from(submissions: submissions, progress: progress);

/// 本物のフォルダを掘らずに「書けた」を記録する。
class _RecordingWriter {
  final Map<String, Uint8List> written = {};

  Future<String> call(
    String directory,
    String fileName,
    Uint8List bytes,
  ) async {
    final path = '$directory/$fileName';
    written[path] = bytes;
    return path;
  }
}

Future<void> _pumpDialog(
  WidgetTester tester, {
  required AppDependencies dependencies,
  required ReviewQueue queue,
  required Future<String?> Function() chooseDirectory,
  required BulkExportFileWriter writeFile,
}) async {
  await tester.pumpWidget(
    wrapWithDependencies(
      MaterialApp(
        theme: AppTheme.light(),
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: FilledButton(
                onPressed: () => showBulkExportDialog(
                  context,
                  testId: 'test-1',
                  queue: queue,
                  chooseDirectory: chooseDirectory,
                  writeFile: writeFile,
                  pollInterval: const Duration(milliseconds: 10),
                ),
                child: const Text('open'),
              ),
            ),
          ),
        ),
      ),
      dependencies: dependencies,
    ),
  );
  await tester.tap(find.text('open'));
  await tester.pump();
}

void main() {
  group('BulkExportPlan', () {
    test('全設問が確定した答案だけを対象にし、対象外は理由付きで残す', () {
      final plan = BulkExportPlan.from(
        _queue(
          submissions: [
            _submission(id: 'sub-1', label: '出席1'),
            _submission(id: 'sub-2', label: '出席2', day: 2),
            _submission(id: 'sub-3', label: '出席3', day: 3),
          ],
          progress: [
            _progress(id: 'sub-1'),
            _progress(id: 'sub-2', confirmed: 1),
            _progress(id: 'sub-3'),
          ],
        ),
      );

      expect(plan.targets.map((target) => target.submissionId), [
        'sub-1',
        'sub-3',
      ]);
      expect(plan.excluded.single.submissionId, 'sub-2');
      expect(plan.excluded.single.reason, contains('未確認の設問が1問'));
    });

    test('進捗が取れていない答案は、確定済みだと決めつけずに対象外にする', () {
      // `listReviewProgress` が落ちると総設問数が0で届く。ここで対象に
      // 入れると「押せるのに必ず断られる」出力になる (Issue #137 と同じ判断)。
      final plan = BulkExportPlan.from(
        _queue(
          submissions: [_submission(id: 'sub-1')],
          progress: const [],
        ),
      );

      expect(plan.targets, isEmpty);
      expect(plan.excluded.single.reason, contains('取れていません'));
    });
  });

  group('BulkExportRunner', () {
    test('答案ごとに1ファイルへ分けて書き、名前はサイドカーの命名を踏襲する', () async {
      final writer = _RecordingWriter();
      final dependencies = AppDependencies(
        requestBulkExport: (testId, {submissionIds}) async => _response([
          _item(
            submissionId: 'sub-1',
            status: BulkExportItemStatus.queued,
            jobId: 'job-1',
          ),
          _item(
            submissionId: 'sub-2',
            status: BulkExportItemStatus.queued,
            jobId: 'job-2',
          ),
        ]),
        getJob: (jobId) async => _job(id: jobId, state: 'succeeded'),
        listExports: (submissionId) async => [
          _export(
            id: 'export-$submissionId',
            submissionId: submissionId,
            jobId: submissionId == 'sub-1' ? 'job-1' : 'job-2',
            filePath: 'exports/${submissionId}_corrected.pdf',
          ),
        ],
        getExportFile: (exportId) async => Uint8List.fromList([1, 2, 3]),
      );

      final result =
          await BulkExportRunner(
            dependencies: dependencies,
            writeFile: writer.call,
            pollInterval: const Duration(milliseconds: 1),
          ).run(
            testId: 'test-1',
            targets: const [
              BulkExportTarget(submissionId: 'sub-1', label: '出席1'),
              BulkExportTarget(submissionId: 'sub-2', label: '出席2'),
            ],
            destinationDirectory: '/out',
          );

      expect(result.writtenCount, 2);
      expect(result.failures, isEmpty);
      expect(writer.written.keys, [
        '/out/sub-1_corrected.pdf',
        '/out/sub-2_corrected.pdf',
      ]);
    });

    test('1件が断られても、残りは出し切って失敗一覧に理由が残る', () async {
      final writer = _RecordingWriter();
      final dependencies = AppDependencies(
        requestBulkExport: (testId, {submissionIds}) async => _response([
          _item(
            submissionId: 'sub-1',
            status: BulkExportItemStatus.refused,
            refusalCode: ExportRefusalReason.unconfirmedQuestions,
            refusalQuestionIds: const ['q-1', 'q-2'],
          ),
          _item(
            submissionId: 'sub-2',
            status: BulkExportItemStatus.queued,
            jobId: 'job-2',
          ),
        ]),
        getJob: (jobId) async => _job(id: jobId, state: 'succeeded'),
        listExports: (submissionId) async => [
          _export(
            id: 'export-2',
            submissionId: 'sub-2',
            jobId: 'job-2',
            filePath: 'exports/sub-2_corrected.pdf',
          ),
        ],
        getExportFile: (exportId) async => Uint8List.fromList([1]),
      );

      final result =
          await BulkExportRunner(
            dependencies: dependencies,
            writeFile: writer.call,
            pollInterval: const Duration(milliseconds: 1),
          ).run(
            testId: 'test-1',
            targets: const [
              BulkExportTarget(submissionId: 'sub-1', label: '出席1'),
              BulkExportTarget(submissionId: 'sub-2', label: '出席2'),
            ],
            destinationDirectory: '/out',
          );

      expect(result.writtenCount, 1);
      expect(writer.written.keys, ['/out/sub-2_corrected.pdf']);
      expect(result.failures.single.target.submissionId, 'sub-1');
      expect(result.failures.single.failureReason, contains('未確認の設問が2問'));
      expect(result.retryableTargets.single.submissionId, 'sub-1');
    });

    test('ジョブが途中で失敗しても止まらず、その1件だけが失敗として残る', () async {
      final writer = _RecordingWriter();
      final dependencies = AppDependencies(
        requestBulkExport: (testId, {submissionIds}) async => _response([
          for (final id in ['sub-1', 'sub-2', 'sub-3'])
            _item(
              submissionId: id,
              status: BulkExportItemStatus.queued,
              jobId: 'job-$id',
            ),
        ]),
        getJob: (jobId) async => jobId == 'job-sub-2'
            ? _job(id: jobId, state: 'failed', lastError: 'PDFを描画できません')
            : _job(id: jobId, state: 'succeeded'),
        listExports: (submissionId) async => [
          _export(
            id: 'export-$submissionId',
            submissionId: submissionId,
            jobId: 'job-$submissionId',
            filePath: 'exports/${submissionId}_corrected.pdf',
          ),
        ],
        getExportFile: (exportId) async => Uint8List.fromList([1]),
      );

      final result =
          await BulkExportRunner(
            dependencies: dependencies,
            writeFile: writer.call,
            pollInterval: const Duration(milliseconds: 1),
          ).run(
            testId: 'test-1',
            targets: const [
              BulkExportTarget(submissionId: 'sub-1', label: '出席1'),
              BulkExportTarget(submissionId: 'sub-2', label: '出席2'),
              BulkExportTarget(submissionId: 'sub-3', label: '出席3'),
            ],
            destinationDirectory: '/out',
          );

      expect(writer.written.keys, [
        '/out/sub-1_corrected.pdf',
        '/out/sub-3_corrected.pdf',
      ]);
      expect(result.failures.single.target.submissionId, 'sub-2');
      expect(result.failures.single.failureReason, 'PDFを描画できません');
    });

    test('書き込みが失敗した答案も、残りを道連れにしない', () async {
      // USBが抜けた・権限が無い、を想定。ここで例外が抜けると残り39枚が
      // 消える。
      final dependencies = AppDependencies(
        requestBulkExport: (testId, {submissionIds}) async => _response([
          for (final id in ['sub-1', 'sub-2'])
            _item(
              submissionId: id,
              status: BulkExportItemStatus.queued,
              jobId: 'job-$id',
            ),
        ]),
        getJob: (jobId) async => _job(id: jobId, state: 'succeeded'),
        listExports: (submissionId) async => [
          _export(
            id: 'export-$submissionId',
            submissionId: submissionId,
            jobId: 'job-$submissionId',
            filePath: 'exports/${submissionId}_corrected.pdf',
          ),
        ],
        getExportFile: (exportId) async => Uint8List.fromList([1]),
      );

      final result =
          await BulkExportRunner(
            dependencies: dependencies,
            writeFile: (directory, fileName, bytes) async {
              if (fileName.startsWith('sub-1')) {
                throw const FileSystemException('読み取り専用です');
              }
              return '$directory/$fileName';
            },
            pollInterval: const Duration(milliseconds: 1),
          ).run(
            testId: 'test-1',
            targets: const [
              BulkExportTarget(submissionId: 'sub-1', label: '出席1'),
              BulkExportTarget(submissionId: 'sub-2', label: '出席2'),
            ],
            destinationDirectory: '/out',
          );

      expect(result.writtenCount, 1);
      expect(result.failures.single.target.submissionId, 'sub-1');
      expect(result.failures.single.failureReason, contains('書き込めません'));
    });

    test('既に出力済みの答案は再描画せず、記録済みのファイルをそのまま書き出す', () async {
      final writer = _RecordingWriter();
      var jobCalls = 0;
      final dependencies = AppDependencies(
        requestBulkExport: (testId, {submissionIds}) async => _response([
          _item(
            submissionId: 'sub-1',
            status: BulkExportItemStatus.reused,
            export: _export(
              id: 'export-1',
              submissionId: 'sub-1',
              jobId: 'job-old',
              filePath: 'exports/sub-1_corrected.pdf',
            ),
          ),
        ]),
        getJob: (jobId) async {
          jobCalls += 1;
          return _job(id: jobId, state: 'succeeded');
        },
        getExportFile: (exportId) async => Uint8List.fromList([9]),
      );

      final result =
          await BulkExportRunner(
            dependencies: dependencies,
            writeFile: writer.call,
            pollInterval: const Duration(milliseconds: 1),
          ).run(
            testId: 'test-1',
            targets: const [
              BulkExportTarget(submissionId: 'sub-1', label: '出席1'),
            ],
            destinationDirectory: '/out',
          );

      expect(result.writtenCount, 1);
      expect(writer.written.keys.single, '/out/sub-1_corrected.pdf');
      expect(jobCalls, 0, reason: 'reused はジョブを待たない');
    });

    test('中止すると、まだ始まっていないジョブをサイドカー側でも取り消す', () async {
      final cancelled = <String>[];
      late BulkExportRunner runner;
      final dependencies = AppDependencies(
        requestBulkExport: (testId, {submissionIds}) async => _response([
          for (final id in ['sub-1', 'sub-2'])
            _item(
              submissionId: id,
              status: BulkExportItemStatus.queued,
              jobId: 'job-$id',
            ),
        ]),
        getJob: (jobId) async {
          // 1件目を見た時点で講師が中止を押した、という筋書き。
          runner.cancel();
          return _job(id: jobId, state: 'queued');
        },
        cancelJob: (jobId) async {
          cancelled.add(jobId);
          return _job(id: jobId, state: 'cancelled');
        },
      );
      runner = BulkExportRunner(
        dependencies: dependencies,
        writeFile: _RecordingWriter().call,
        pollInterval: const Duration(milliseconds: 1),
      );

      final result = await runner.run(
        testId: 'test-1',
        targets: const [
          BulkExportTarget(submissionId: 'sub-1', label: '出席1'),
          BulkExportTarget(submissionId: 'sub-2', label: '出席2'),
        ],
        destinationDirectory: '/out',
      );

      expect(cancelled, ['job-sub-1', 'job-sub-2']);
      expect(result.cancelled, hasLength(2));
      // 自分で止めたものを「失敗」と報告しない。
      expect(result.failures, isEmpty);
      expect(result.retryableTargets, hasLength(2));
    });

    test('一括出力の要求そのものが失敗したら、全件を同じ理由で失敗にする', () async {
      // 黙って空の結果を返すと「対象が0件だった」と読めてしまう。
      final result =
          await BulkExportRunner(
            dependencies: AppDependencies(
              requestBulkExport: (testId, {submissionIds}) async =>
                  throw SidecarApiException(
                    SidecarErrorKind.unavailable,
                    'sidecar is not connected',
                  ),
            ),
            writeFile: _RecordingWriter().call,
            pollInterval: const Duration(milliseconds: 1),
          ).run(
            testId: 'test-1',
            targets: const [
              BulkExportTarget(submissionId: 'sub-1', label: '出席1'),
              BulkExportTarget(submissionId: 'sub-2', label: '出席2'),
            ],
            destinationDirectory: '/out',
          );

      expect(result.failures, hasLength(2));
      expect(result.writtenCount, 0);
    });
  });

  group('BulkExportDialog', () {
    testWidgets('対象確認 → 出力先選択 → 進捗 → 完了、を通しで進む', (tester) async {
      final writer = _RecordingWriter();
      var chooseCalls = 0;
      var jobState = 'queued';
      final dependencies = AppDependencies(
        requestBulkExport: (testId, {submissionIds}) async => _response([
          _item(
            submissionId: 'sub-1',
            status: BulkExportItemStatus.queued,
            jobId: 'job-1',
          ),
        ]),
        getJob: (jobId) async => _job(id: jobId, state: jobState),
        listExports: (submissionId) async => [
          _export(
            id: 'export-1',
            submissionId: 'sub-1',
            jobId: 'job-1',
            filePath: 'exports/sub-1_corrected.pdf',
          ),
        ],
        getExportFile: (exportId) async => Uint8List.fromList([1]),
      );

      await _pumpDialog(
        tester,
        dependencies: dependencies,
        queue: _queue(
          submissions: [
            _submission(id: 'sub-1', label: '出席1'),
            _submission(id: 'sub-2', label: '出席2', day: 2),
          ],
          progress: [
            _progress(id: 'sub-1'),
            _progress(id: 'sub-2', confirmed: 0),
          ],
        ),
        chooseDirectory: () async {
          chooseCalls += 1;
          return '/out';
        },
        writeFile: writer.call,
      );

      // 1. 走り出す前に、何件出て何件出ないかが見えている。
      expect(find.byKey(const Key('bulk-export-confirm')), findsOne);
      expect(find.text('対象 1件'), findsOne);
      expect(find.text('対象外 1件'), findsOne);
      expect(find.textContaining('出席2: 未確認の設問が2問'), findsOne);
      expect(writer.written, isEmpty, reason: '確認の段では1バイトも書かない');

      // 2. 出力先は1回だけ選ばせる。
      await tester.tap(find.byKey(const Key('bulk-export-start-button')));
      await tester.pump();
      expect(chooseCalls, 1);

      // 3. 進捗が「n / 全件」と、いま出している答案で見えている。
      await tester.pump(const Duration(milliseconds: 5));
      expect(find.byKey(const Key('bulk-export-progress')), findsOne);
      expect(find.text('0 / 1 件'), findsOne);
      expect(find.text('出力中: 出席1'), findsOne);
      expect(find.byKey(const Key('bulk-export-cancel-button')), findsOne);

      // 4. 終わると保存先と件数が出る。
      jobState = 'succeeded';
      await tester.pump(const Duration(milliseconds: 20));
      await tester.pumpAndSettle();
      expect(find.byKey(const Key('bulk-export-result')), findsOne);
      expect(find.text('1 / 1 件を出力しました。'), findsOne);
      expect(find.text('保存先: /out'), findsOne);
      expect(writer.written.keys.single, '/out/sub-1_corrected.pdf');
    });

    testWidgets('失敗した答案は理由付きで並び、その分だけ再実行できる', (tester) async {
      final writer = _RecordingWriter();
      final requestedBatches = <List<String>?>[];
      var attempt = 0;
      final dependencies = AppDependencies(
        requestBulkExport: (testId, {submissionIds}) async {
          requestedBatches.add(submissionIds);
          attempt += 1;
          if (attempt == 1) {
            return _response([
              _item(
                submissionId: 'sub-1',
                status: BulkExportItemStatus.queued,
                jobId: 'job-1',
              ),
              _item(
                submissionId: 'sub-2',
                status: BulkExportItemStatus.refused,
                refusalCode: ExportRefusalReason.noRoomForScore,
                refusalQuestionIds: const ['q-9'],
              ),
            ]);
          }
          return _response([
            _item(
              submissionId: 'sub-2',
              status: BulkExportItemStatus.queued,
              jobId: 'job-2',
            ),
          ]);
        },
        getJob: (jobId) async => _job(id: jobId, state: 'succeeded'),
        listExports: (submissionId) async => [
          _export(
            id: 'export-$submissionId',
            submissionId: submissionId,
            jobId: submissionId == 'sub-1' ? 'job-1' : 'job-2',
            filePath: 'exports/${submissionId}_corrected.pdf',
          ),
        ],
        getExportFile: (exportId) async => Uint8List.fromList([1]),
      );

      await _pumpDialog(
        tester,
        dependencies: dependencies,
        queue: _queue(
          submissions: [
            _submission(id: 'sub-1', label: '出席1'),
            _submission(id: 'sub-2', label: '出席2', day: 2),
          ],
          progress: [
            _progress(id: 'sub-1'),
            _progress(id: 'sub-2'),
          ],
        ),
        chooseDirectory: () async => '/out',
        writeFile: writer.call,
      );
      await tester.tap(find.byKey(const Key('bulk-export-start-button')));
      await tester.pumpAndSettle();

      expect(find.text('1 / 2 件を出力しました。'), findsOne);
      expect(find.byKey(const Key('bulk-export-failures')), findsOne);
      expect(find.textContaining('出席2: 点数を書き込める場所がありません'), findsOne);

      // 失敗した1件だけを、同じ出力先へ出し直す -- フォルダは選び直さない。
      await tester.tap(find.byKey(const Key('bulk-export-retry-button')));
      await tester.pumpAndSettle();

      expect(requestedBatches, [
        ['sub-1', 'sub-2'],
        ['sub-2'],
      ]);
      expect(find.text('1 / 1 件を出力しました。'), findsOne);
      expect(writer.written.keys, [
        '/out/sub-1_corrected.pdf',
        '/out/sub-2_corrected.pdf',
      ]);
    });

    testWidgets('対象が0件のときは、なぜ0件かを出して開始させない', (tester) async {
      var chooseCalls = 0;
      await _pumpDialog(
        tester,
        dependencies: const AppDependencies(),
        queue: _queue(
          submissions: [
            _submission(id: 'sub-1', label: '出席1'),
            _submission(id: 'sub-2', label: '出席2', day: 2),
          ],
          progress: [
            _progress(id: 'sub-1', confirmed: 0),
            _progress(id: 'sub-2', confirmed: 1),
          ],
        ),
        chooseDirectory: () async {
          chooseCalls += 1;
          return '/out';
        },
        writeFile: (directory, fileName, bytes) async =>
            fail('対象が0件なのに書き出そうとした'),
      );

      expect(find.byKey(const Key('bulk-export-empty')), findsOne);
      expect(find.textContaining('出力できる答案がありません'), findsOne);
      // **なぜ0件かまで出す。** 件数だけでは次に何をすればよいか分からない。
      expect(find.text('対象外 2件'), findsOne);
      expect(find.textContaining('出席1: 未確認の設問が2問'), findsOne);
      expect(find.textContaining('出席2: 未確認の設問が1問'), findsOne);

      final startButton = tester.widget<FilledButton>(
        find.byKey(const Key('bulk-export-start-button')),
      );
      expect(startButton.onPressed, isNull);
      expect(chooseCalls, 0);
    });

    testWidgets('答案が1件も無いテストでは、確定を促さない', (tester) async {
      await _pumpDialog(
        tester,
        dependencies: const AppDependencies(),
        queue: _queue(submissions: const [], progress: const []),
        chooseDirectory: () async => '/out',
        writeFile: (directory, fileName, bytes) async => fail('書き出した'),
      );

      expect(find.text('このテストにはまだ答案がありません。'), findsOne);
      expect(find.byKey(const Key('bulk-export-excluded')), findsNothing);
    });
  });
}
