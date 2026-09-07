import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/features/pdf_review/export_dialog.dart';

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
    MaterialApp(
      home: Builder(
        builder: (context) => Scaffold(
          body: Center(
            child: FilledButton(
              onPressed: () => showExportDialog(
                context,
                dependencies: dependencies,
                submissionId: 'sub-1',
              ),
              child: const Text('open'),
            ),
          ),
        ),
      ),
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
}
