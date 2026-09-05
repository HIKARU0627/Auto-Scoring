import 'dart:async';

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

  testWidgets(
    'a completed retry is not overwritten by a stale in-flight list response',
    (tester) async {
      final listCompleter = Completer<List<SubmissionResponse>>();
      final dependencies = AppDependencies(
        listTests: () async => [_test()],
        listSubmissions: (testId) => listCompleter.future,
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
      // listSubmissions() is now in flight, unresolved -- from here on use
      // pump(duration), not pumpAndSettle(): the loading spinner's
      // indeterminate animation never settles on its own and would hang it.
      await tester.pump(const Duration(milliseconds: 50));

      await tester.tap(find.text('ファイルを選択'));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.tap(find.text('取り込む'));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump(const Duration(milliseconds: 50));

      // The retry (createSubmission) already landed locally as ai_processed.
      expect(find.textContaining('処理済み'), findsWidgets);

      // The list fetch that started before the retry succeeded finally
      // resolves -- with a *stale* snapshot that still shows this same
      // submission id in `error`. That must not clobber the fresher local
      // copy just because the id already exists in the fetched response.
      listCompleter.complete([_submission(state: 'error')]);
      await tester.pumpAndSettle();

      expect(find.byType(ListTile), findsOneWidget);
      expect(find.textContaining('エラー'), findsNothing);
      expect(find.textContaining('処理済み'), findsWidgets);
    },
  );

  testWidgets('retrying a list-load failure reloads the list, not an upload', (
    tester,
  ) async {
    var test2ListAttempts = 0;
    var createSubmissionCalls = 0;
    final dependencies = AppDependencies(
      listTests: () async => [
        _test(id: 'test-1', name: '国語 第1回'),
        _test(id: 'test-2', name: '算数 第1回'),
      ],
      listSubmissions: (testId) async {
        if (testId == 'test-1') return const [];
        test2ListAttempts++;
        if (test2ListAttempts == 1) {
          throw SidecarApiException(SidecarErrorKind.badResponse, 'list失敗');
        }
        return const [];
      },
      createSubmission:
          ({required testId, required filePath, studentLabel}) async {
            createSubmissionCalls++;
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

    // A file is picked while test-1 (whose list loaded fine) is selected --
    // switching tests below doesn't clear it, so it's still present when
    // the new test's list load fails.
    await tester.tap(find.text('ファイルを選択'));
    await tester.pumpAndSettle();
    expect(find.text('student-a.pdf'), findsOneWidget);

    await tester.tap(find.byKey(const Key('test-picker')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('算数 第1回').last);
    await tester.pumpAndSettle();

    expect(find.text('list失敗'), findsOneWidget);
    expect(test2ListAttempts, 1);

    // If the retry button called _submit instead of reloading the list, this
    // would upload the still-picked file instead.
    await tester.tap(find.text('再試行'));
    await tester.pumpAndSettle();

    expect(test2ListAttempts, 2);
    expect(createSubmissionCalls, 0);
    expect(find.text('list失敗'), findsNothing);
  });

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

  testWidgets('the test picker is disabled while an upload is in flight', (
    tester,
  ) async {
    final uploadStarted = Completer<void>();
    final releaseUpload = Completer<SubmissionResponse>();
    final dependencies = AppDependencies(
      listTests: () async => [_test()],
      listSubmissions: (testId) async => const [],
      createSubmission:
          ({required testId, required filePath, studentLabel}) async {
            uploadStarted.complete();
            return releaseUpload.future;
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
    await tester.pump();
    await uploadStarted.future;
    await tester.pump();

    final picker = tester.widget<DropdownButtonFormField<String>>(
      find.byKey(const Key('test-picker')),
    );
    expect(picker.onChanged, isNull);

    releaseUpload.complete(_submission());
    await tester.pumpAndSettle();

    final pickerAfter = tester.widget<DropdownButtonFormField<String>>(
      find.byKey(const Key('test-picker')),
    );
    expect(pickerAfter.onChanged, isNotNull);
  });

  testWidgets(
    'the file picker button and student-label field are disabled while an upload is in flight',
    (tester) async {
      final uploadStarted = Completer<void>();
      final releaseUpload = Completer<SubmissionResponse>();
      final dependencies = AppDependencies(
        listTests: () async => [_test()],
        listSubmissions: (testId) async => const [],
        createSubmission:
            ({required testId, required filePath, studentLabel}) async {
              uploadStarted.complete();
              return releaseUpload.future;
            },
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
      await tester.tap(find.text('ファイルを選択'));
      await tester.pumpAndSettle();

      await tester.tap(find.text('取り込む'));
      await tester.pump();
      await uploadStarted.future;
      await tester.pump();

      final filePickerButton = tester.widget<OutlinedButton>(
        find.widgetWithText(OutlinedButton, 'ファイルを選択'),
      );
      expect(filePickerButton.onPressed, isNull);
      final studentLabelField = tester.widget<TextField>(
        find.byType(TextField),
      );
      expect(studentLabelField.enabled, isFalse);

      releaseUpload.complete(_submission());
      await tester.pumpAndSettle();

      final filePickerButtonAfter = tester.widget<OutlinedButton>(
        find.widgetWithText(OutlinedButton, 'ファイルを選択'),
      );
      expect(filePickerButtonAfter.onPressed, isNotNull);
      final studentLabelFieldAfter = tester.widget<TextField>(
        find.byType(TextField),
      );
      expect(studentLabelFieldAfter.enabled, isTrue);
    },
  );

  testWidgets(
    'disposing the page while a file pick is still pending does not throw',
    (tester) async {
      // Regression test: _pickFile must check `mounted` after `await
      // widget.pickFile()` before touching setState -- otherwise navigating
      // away while the native file dialog is still open crashes with
      // "setState() called after dispose()".
      final pickCompleter = Completer<PickedPdfFile?>();
      final dependencies = AppDependencies(
        listTests: () async => [_test()],
        listSubmissions: (testId) async => const [],
      );

      await tester.pumpWidget(
        _wrap(
          AnswerIntakePage(
            dependencies: dependencies,
            pickFile: () => pickCompleter.future,
          ),
        ),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('test-picker')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('国語 第1回').last);
      await tester.pumpAndSettle();

      await tester.tap(find.text('ファイルを選択'));
      await tester.pump();

      await tester.pumpWidget(const MaterialApp(home: SizedBox()));
      await tester.pumpAndSettle();

      pickCompleter.complete(
        const PickedPdfFile(
          path: 'C:/tmp/student-a.pdf',
          name: 'student-a.pdf',
        ),
      );
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
    },
  );

  testWidgets(
    'a submission created while the list is still loading is not lost when the stale list response lands',
    (tester) async {
      final listCompleter = Completer<List<SubmissionResponse>>();
      final dependencies = AppDependencies(
        listTests: () async => [_test()],
        listSubmissions: (testId) => listCompleter.future,
        createSubmission:
            ({required testId, required filePath, studentLabel}) async =>
                _submission(id: 'sub-new'),
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
      // listSubmissions() is now in flight, unresolved -- from here on use
      // pump(duration), not pumpAndSettle(): the loading spinner's
      // indeterminate animation never settles on its own and would hang it.
      await tester.pump(const Duration(milliseconds: 50));

      await tester.tap(find.text('ファイルを選択'));
      await tester.pump(const Duration(milliseconds: 50));
      expect(find.text('student-a.pdf'), findsOneWidget);

      await tester.tap(find.text('取り込む'));
      await tester.pump(const Duration(milliseconds: 50));
      await tester.pump(const Duration(milliseconds: 50));

      // The list fetch that started before this submission existed finally
      // lands (empty, since it predates the submission); it must not wipe
      // the freshly created submission back out of the list.
      listCompleter.complete(const []);
      await tester.pumpAndSettle();

      expect(find.byType(ListTile), findsOneWidget);
      expect(find.text('取込完了: 処理済み'), findsOneWidget);
    },
  );

  testWidgets('a short viewport does not overflow the intake form', (
    tester,
  ) async {
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);
    tester.view.physicalSize = const Size(400, 320);
    tester.view.devicePixelRatio = 1.0;

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

    expect(tester.takeException(), isNull);
  });

  testWidgets(
    'the default (unconnected) dependencies show an error instead of crashing on mount',
    (tester) async {
      // Regression test: AppDependencies()'s default listTests/listSubmissions
      // /createSubmission must report failure as a rejected Future, not throw
      // synchronously -- a synchronous throw during initState's
      // `widget.dependencies.listTests()` call would crash while the widget
      // is still mounting instead of reaching FutureBuilder's error branch.
      await tester.pumpWidget(
        _wrap(AnswerIntakePage(dependencies: const AppDependencies())),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('test-list-error')), findsOneWidget);
      expect(tester.takeException(), isNull);
    },
  );
}
