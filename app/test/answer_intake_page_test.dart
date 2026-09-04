import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/features/answer_intake/answer_intake_page.dart';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter_test/flutter_test.dart';

SubmissionResponse _submission({
  String id = 'sub-1',
  String state = 'ai_processed',
  String? studentLabel = 'student-a',
  String? reviewReason,
}) {
  return SubmissionResponse(
    (b) => b
      ..id = id
      ..testId = 'test-1'
      ..state = state
      ..pageCount = 1
      ..studentLabel = studentLabel
      ..reviewReason = reviewReason
      ..createdAt = DateTime.utc(2026, 1, 1),
  );
}

TestSummary _test({String id = 'test-1', String name = '国語 第1回'}) {
  return TestSummary(
    (b) => b
      ..id = id
      ..name = name,
  );
}

Future<PickedPdfFile?> _fakePick() async =>
    const PickedPdfFile(path: 'C:/tmp/student-a.pdf', name: 'student-a.pdf');

Widget _wrap(AnswerIntakePage page) => MaterialApp(home: page);

void main() {
  testWidgets('lists tests, uploads a file, and shows the result', (
    tester,
  ) async {
    var listSubmissionsCalls = 0;
    final dependencies = AppDependencies(
      listTests: () async => [_test()],
      listSubmissions: (testId) async {
        listSubmissionsCalls++;
        return const [];
      },
      createSubmission:
          ({required testId, required filePath, studentLabel}) async {
            expect(testId, 'test-1');
            expect(filePath, 'C:/tmp/student-a.pdf');
            await Future<void>.delayed(const Duration(milliseconds: 20));
            return _submission();
          },
    );

    await tester.pumpWidget(
      _wrap(AnswerIntakePage(dependencies: dependencies, pickFile: _fakePick)),
    );
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('test-picker')), findsOneWidget);
    await tester.tap(find.byKey(const Key('test-picker')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('国語 第1回').last);
    await tester.pumpAndSettle();
    expect(listSubmissionsCalls, 1);

    await tester.tap(find.text('ファイルを選択'));
    await tester.pumpAndSettle();
    expect(find.text('student-a.pdf'), findsOneWidget);

    await tester.tap(find.text('取り込む'));
    await tester.pump(); // start the async upload
    expect(find.byType(LinearProgressIndicator), findsOneWidget);
    await tester.pumpAndSettle();

    expect(find.text('取込完了: 処理済み'), findsOneWidget);
    expect(find.text('student-a'), findsOneWidget);
  });

  testWidgets('shows an error banner with a working retry action', (
    tester,
  ) async {
    var attempts = 0;
    final dependencies = AppDependencies(
      listTests: () async => [_test()],
      listSubmissions: (testId) async => const [],
      createSubmission:
          ({required testId, required filePath, studentLabel}) async {
            attempts++;
            if (attempts == 1) {
              throw SidecarApiException(
                SidecarErrorKind.badResponse,
                'file size 999 exceeds limit 500',
                statusCode: 413,
              );
            }
            return _submission();
          },
    );

    await tester.pumpWidget(
      _wrap(AnswerIntakePage(dependencies: dependencies, pickFile: _fakePick)),
    );
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('test-picker')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('国語 第1回').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('ファイルを選択'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('取り込む'));
    await tester.pumpAndSettle();

    expect(find.text('file size 999 exceeds limit 500'), findsOneWidget);
    expect(attempts, 1);

    await tester.tap(find.text('再試行'));
    await tester.pumpAndSettle();

    expect(attempts, 2);
    expect(find.text('file size 999 exceeds limit 500'), findsNothing);
    expect(find.text('取込完了: 処理済み'), findsOneWidget);
  });

  testWidgets('surfaces a duplicate submission as a friendly message', (
    tester,
  ) async {
    final dependencies = AppDependencies(
      listTests: () async => [_test()],
      listSubmissions: (testId) async => const [],
      createSubmission:
          ({required testId, required filePath, studentLabel}) async =>
              throw DuplicateSubmissionException('duplicate', 'sub-99'),
    );

    await tester.pumpWidget(
      _wrap(AnswerIntakePage(dependencies: dependencies, pickFile: _fakePick)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('test-picker')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('国語 第1回').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('ファイルを選択'));
    await tester.pumpAndSettle();
    await tester.tap(find.text('取り込む'));
    await tester.pumpAndSettle();

    expect(find.textContaining('sub-99'), findsOneWidget);
  });

  testWidgets('renders needs_review submissions with their reason', (
    tester,
  ) async {
    final dependencies = AppDependencies(
      listTests: () async => [_test()],
      listSubmissions: (testId) async => [
        _submission(state: 'needs_review', reviewReason: 'missing_pages:2'),
      ],
    );

    await tester.pumpWidget(
      _wrap(AnswerIntakePage(dependencies: dependencies, pickFile: _fakePick)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('test-picker')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('国語 第1回').last);
    await tester.pumpAndSettle();

    expect(find.textContaining('要確認'), findsOneWidget);
    expect(find.textContaining('missing_pages:2'), findsOneWidget);
  });

  testWidgets(
    'a successful retry replaces the errored row instead of duplicating it',
    (tester) async {
      final dependencies = AppDependencies(
        listTests: () async => [_test()],
        listSubmissions: (testId) async => [_submission(state: 'error')],
        createSubmission:
            ({required testId, required filePath, studentLabel}) async =>
                _submission(state: 'ai_processed'),
      );

      await tester.pumpWidget(
        _wrap(
          AnswerIntakePage(dependencies: dependencies, pickFile: _fakePick),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('test-picker')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('国語 第1回').last);
      await tester.pumpAndSettle();

      expect(find.textContaining('エラー'), findsOneWidget);

      await tester.tap(find.text('ファイルを選択'));
      await tester.pumpAndSettle();
      await tester.tap(find.text('取り込む'));
      await tester.pumpAndSettle();

      // Same submission id (sub-1 by default) succeeded: exactly one row for
      // it, showing the new state, not two (stale error + fresh success).
      expect(find.byType(ListTile), findsOneWidget);
      expect(find.textContaining('エラー'), findsNothing);
      expect(find.textContaining('処理済み'), findsWidgets);
    },
  );

  testWidgets('submitting the student-label field with Enter uploads', (
    tester,
  ) async {
    var uploaded = false;
    final dependencies = AppDependencies(
      listTests: () async => [_test()],
      listSubmissions: (testId) async => const [],
      createSubmission:
          ({required testId, required filePath, studentLabel}) async {
            uploaded = true;
            expect(studentLabel, 'たろう');
            return _submission();
          },
    );

    await tester.pumpWidget(
      _wrap(AnswerIntakePage(dependencies: dependencies, pickFile: _fakePick)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('test-picker')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('国語 第1回').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('ファイルを選択'));
    await tester.pumpAndSettle();

    await tester.enterText(find.byType(TextField), 'たろう');
    await tester.testTextInput.receiveAction(TextInputAction.done);
    await tester.pumpAndSettle();

    expect(uploaded, isTrue);
  });

  testWidgets('the submit button is reachable and activatable by keyboard', (
    tester,
  ) async {
    var uploaded = false;
    final dependencies = AppDependencies(
      listTests: () async => [_test()],
      listSubmissions: (testId) async => const [],
      createSubmission:
          ({required testId, required filePath, studentLabel}) async {
            uploaded = true;
            return _submission();
          },
    );

    await tester.pumpWidget(
      _wrap(AnswerIntakePage(dependencies: dependencies, pickFile: _fakePick)),
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('test-picker')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('国語 第1回').last);
    await tester.pumpAndSettle();
    await tester.tap(find.text('ファイルを選択'));
    await tester.pumpAndSettle();

    final submitButtonFinder = find.widgetWithText(FilledButton, '取り込む');
    final focusNode = tester
        .widget<FilledButton>(submitButtonFinder)
        .focusNode!;
    focusNode.requestFocus();
    await tester.pumpAndSettle();
    expect(focusNode.hasFocus, isTrue);

    await tester.sendKeyEvent(LogicalKeyboardKey.enter);
    await tester.pumpAndSettle();

    expect(uploaded, isTrue);
  });

  testWidgets('an empty test list explains why nothing can be imported', (
    tester,
  ) async {
    final dependencies = AppDependencies(listTests: () async => const []);

    await tester.pumpWidget(
      _wrap(AnswerIntakePage(dependencies: dependencies, pickFile: _fakePick)),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('登録済みのテストがありません'), findsOneWidget);
  });
}
