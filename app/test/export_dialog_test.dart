import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_theme.dart';
import 'package:auto_scoring_app/features/pdf_review/export_dialog.dart';

import 'app_harness.dart';

JobResponse _job({
  String id = 'job-1',
  String state = 'queued',
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
  String id = 'export-1',
  String jobId = 'job-1',
  String filePath = 'exports/answer_corrected.pdf',
}) => ExportResponse(
  (b) => b
    ..id = id
    ..submissionId = 'sub-1'
    ..jobId = jobId
    ..filePath = filePath
    ..fileSha256 = 'a' * 64
    ..createdAt = DateTime.utc(2026, 1, 1),
);

Future<void> _pumpDialog(
  WidgetTester tester,
  AppDependencies dependencies,
) async {
  await tester.pumpWidget(
    wrapWithDependencies(
      MaterialApp(
        theme: AppTheme.light(),
        home: Builder(
          builder: (context) => Scaffold(
            body: Center(
              child: FilledButton(
                onPressed: () =>
                    showExportDialog(context, submissionId: 'sub-1'),
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
  testWidgets(
    'shows progress, then the saved path once the export job succeeds',
    (tester) async {
      var jobCalls = 0;
      final dependencies = AppDependencies(
        requestExport: (submissionId) async => ExportRequestResponse(
          (b) => b
            ..decision = 'accept_new'
            ..jobId = 'job-1',
        ),
        getJob: (jobId) async {
          jobCalls += 1;
          return _job(state: jobCalls < 2 ? 'running' : 'succeeded');
        },
        listExports: (submissionId) async => [_export()],
      );

      await _pumpDialog(tester, dependencies);

      expect(find.byKey(const Key('export-dialog-progress')), findsOneWidget);

      await tester.pump(const Duration(seconds: 1));
      await tester.pump(const Duration(seconds: 1));
      await tester.pump();

      expect(find.byKey(const Key('export-dialog-success')), findsOneWidget);
      expect(find.textContaining('answer_corrected.pdf'), findsOneWidget);
    },
  );

  testWidgets(
    'hands back the existing export immediately when the review state was already exported',
    (tester) async {
      final dependencies = AppDependencies(
        requestExport: (submissionId) async => ExportRequestResponse(
          (b) => b
            ..decision = 'reuse_existing'
            ..export_.replace(_export(filePath: 'exports/already.pdf')),
        ),
      );

      await _pumpDialog(tester, dependencies);
      await tester.pump();

      expect(find.byKey(const Key('export-dialog-success')), findsOneWidget);
      expect(find.textContaining('already.pdf'), findsOneWidget);
    },
  );

  testWidgets('lists the unconfirmed questions the sidecar refused to export', (
    tester,
  ) async {
    final dependencies = AppDependencies(
      requestExport: (submissionId) async => throw SidecarApiException(
        SidecarErrorKind.conflict,
        'one or more questions are not yet confirmed',
        statusCode: 409,
        unconfirmedQuestionIds: const ['q-1', 'q-2'],
      ),
    );

    await _pumpDialog(tester, dependencies);
    await tester.pump();

    expect(find.byKey(const Key('export-dialog-unconfirmed')), findsOneWidget);
    expect(find.text('・q-1'), findsOneWidget);
    expect(find.text('・q-2'), findsOneWidget);
  });

  testWidgets('a failed export shows a retry action that requeues the job', (
    tester,
  ) async {
    var state = 'running';
    var retried = false;
    final dependencies = AppDependencies(
      requestExport: (submissionId) async => ExportRequestResponse(
        (b) => b
          ..decision = 'accept_new'
          ..jobId = 'job-1',
      ),
      getJob: (jobId) async =>
          _job(state: state, lastError: state == 'failed' ? 'disk full' : null),
      retryJob: (jobId) async {
        retried = true;
        state = 'running';
        return _job(state: 'running');
      },
      listExports: (submissionId) async => [_export()],
    );

    await _pumpDialog(tester, dependencies);
    state = 'failed';
    await tester.pump(const Duration(seconds: 1));
    await tester.pump();

    expect(find.byKey(const Key('export-dialog-error')), findsOneWidget);
    expect(find.textContaining('disk full'), findsOneWidget);

    await tester.tap(find.byKey(const Key('export-dialog-retry-button')));
    await tester.pump();
    expect(retried, isTrue);

    state = 'succeeded';
    await tester.pump(const Duration(seconds: 1));
    await tester.pump();

    expect(find.byKey(const Key('export-dialog-success')), findsOneWidget);
  });

  testWidgets(
    'a transient polling failure resumes observation instead of reporting the export as failed',
    (tester) async {
      var pollAttempts = 0;
      final dependencies = AppDependencies(
        requestExport: (submissionId) async => ExportRequestResponse(
          (b) => b
            ..decision = 'accept_new'
            ..jobId = 'job-1',
        ),
        getJob: (jobId) async {
          pollAttempts += 1;
          if (pollAttempts <= 2) {
            throw SidecarApiException(SidecarErrorKind.timeout, 'timed out');
          }
          return _job(state: 'succeeded');
        },
        listExports: (submissionId) async => [_export()],
      );

      await _pumpDialog(tester, dependencies);

      // Two transient failures -- still just "running", never "failed".
      await tester.pump(const Duration(seconds: 1));
      await tester.pump();
      await tester.pump(const Duration(seconds: 1));
      await tester.pump();
      expect(find.byKey(const Key('export-dialog-progress')), findsOneWidget);
      expect(find.byKey(const Key('export-dialog-error')), findsNothing);

      // Third attempt succeeds.
      await tester.pump(const Duration(seconds: 1));
      await tester.pump();
      expect(find.byKey(const Key('export-dialog-success')), findsOneWidget);
    },
  );

  testWidgets(
    'retrying a cancelled job requests a fresh export instead of retrying the cancelled one',
    (tester) async {
      var requestCount = 0;
      var retryJobCalled = false;
      final dependencies = AppDependencies(
        requestExport: (submissionId) async {
          requestCount += 1;
          return ExportRequestResponse(
            (b) => b
              ..decision = 'accept_new'
              ..jobId = 'job-$requestCount',
          );
        },
        getJob: (jobId) async => _job(state: 'cancelled'),
        retryJob: (jobId) async {
          retryJobCalled = true;
          return _job(state: 'running');
        },
        listExports: (submissionId) async => [_export()],
      );

      await _pumpDialog(tester, dependencies);
      await tester.pump(const Duration(seconds: 1));
      await tester.pump();

      expect(find.byKey(const Key('export-dialog-error')), findsOneWidget);
      expect(requestCount, 1);

      await tester.tap(find.byKey(const Key('export-dialog-retry-button')));
      await tester.pump();

      expect(retryJobCalled, isFalse);
      expect(requestCount, 2);
    },
  );

  testWidgets(
    'eventually reports failure instead of spinning forever when the job keeps '
    'succeeding but its export result can never be fetched',
    (tester) async {
      // P2 review, round 2: `getJob` always succeeding used to reset the
      // transient-failure counter to 0 every poll cycle, before
      // `_loadExportedFile`'s own (at most +1 per cycle) increment ever had
      // a chance to reach the cap -- so this scenario used to poll forever.
      var listExportsAttempts = 0;
      final dependencies = AppDependencies(
        requestExport: (submissionId) async => ExportRequestResponse(
          (b) => b
            ..decision = 'accept_new'
            ..jobId = 'job-1',
        ),
        getJob: (jobId) async => _job(state: 'succeeded'),
        listExports: (submissionId) async {
          listExportsAttempts += 1;
          throw SidecarApiException(SidecarErrorKind.timeout, 'timed out');
        },
      );

      await _pumpDialog(tester, dependencies);

      for (var i = 0; i < 5; i++) {
        await tester.pump(const Duration(seconds: 1));
        await tester.pump();
      }

      expect(find.byKey(const Key('export-dialog-error')), findsOneWidget);
      expect(listExportsAttempts, 5);
    },
  );
}
