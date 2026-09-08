import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/app_dependencies.dart';
import 'package:auto_scoring_app/core/app_routes.dart';
import 'package:auto_scoring_app/core/folder_scan.dart';

import 'app_harness.dart';

/// 資料取込画面 (Issue #101).
///
/// Every acceptance criterion that only exists on screen is pinned here:
///
/// * 5 -- a role can be changed and a file excluded from the list;
/// * 6 -- an unconfirmed AI proposal makes the import action unavailable;
/// * 7 -- the call count and cost are shown before anything is sent;
/// * 8 -- a rule-matched file causes no classification call, asserted as the
///   absence of one against a recording fake.
///
/// It also pins the wording rule from Issue #80's post-mortem: the completion
/// screen must not read as "you can grade now", because points and marking
/// criteria are still missing.
///
/// Every file name here is synthetic.
void main() {
  const digest =
      '0000000000000000000000000000000000000000000000000000000000000000';

  ScannedFolder folder(List<String> paths) => ScannedFolder(
    name: 'batch',
    entries: [
      for (final path in paths)
        ScannedEntry(
          relativePath: path,
          absolutePath: '/tmp/$path',
          sizeBytes: 1,
          sha256: digest,
        ),
    ],
  );

  PlannedFileModel planned(
    String path, {
    MaterialRole? role,
    ClassificationNeed need = ClassificationNeed.notNeeded,
  }) => PlannedFileModel(
    (builder) => builder
      ..relativePath = path
      ..sha256 = digest
      ..sizeBytes = 1
      ..role = role
      ..roleSource = role == null ? RoleSource.unresolved : RoleSource.rule
      ..classification = need,
  );

  IntakePlanResponse plan(
    List<PlannedFileModel> files, {
    int pending = 0,
    List<MaterialRole> missing = const [],
  }) => IntakePlanResponse(
    (builder) => builder
      ..groups.replace([
        PlannedGroupModel(
          (g) => g
            ..key = 'subject-a'
            ..suggestedName = 'subject-a'
            ..missingRequiredRolesIfNew.replace(missing)
            ..files.replace(files),
        ),
      ])
      ..estimate.replace(
        ClassificationEstimateModel(
          (e) => e
            ..pending = pending
            ..cached = 0
            ..unsupported = 0
            ..notNeeded = files.length - pending,
        ),
      ),
  );

  IntakeTemplateModel template() => IntakeTemplateModel(
    (builder) => builder
      ..id = 'serial-number-prefix'
      ..name = '連番の接頭辞 (既定)'
      ..splitChildDirectories = true
      ..rules.replace(const <IntakeRuleModel>[]),
  );

  ClassificationAvailabilityResponse available({bool yes = true}) =>
      ClassificationAvailabilityResponse(
        (builder) => builder
          ..available = yes
          ..reason = yes ? null : 'この端末には provider が設定されていません',
      );

  /// The two files a complete new test needs, both matched by a rule.
  final ruleMatched = [
    planned('subject-a/01_answers.pdf', role: MaterialRole.studentAnswer),
    planned('subject-a/02_criteria.pdf', role: MaterialRole.gradingCriteria),
  ];

  Future<void> openReview(
    WidgetTester tester, {
    required IntakePlanResponse withPlan,
    required List<String> paths,
    AppDependencies? dependencies,
    double? unitCost,
    bool classificationAvailable = true,
  }) async {
    await pumpAppAt(
      tester,
      AppRoutes.intake,
      dependencies:
          dependencies ??
          AppDependencies(
            listIntakeTemplates: () async => [template()],
            intakeCost: () async => unitCost,
            listTests: () async => const [],
            classificationAvailability: () async =>
                available(yes: classificationAvailable),
            planIntake:
                ({
                  required templateId,
                  required rootName,
                  required files,
                }) async => withPlan,
          ),
      overrides: [
        chooseFolderProvider.overrideWithValue(() async => '/tmp/batch'),
        scanFolderProvider.overrideWithValue((_) async => folder(paths)),
      ],
    );
    await tester.pumpAndSettle();
    await tester.tap(find.byKey(const Key('intake-choose-folder')));
    await tester.pumpAndSettle();
  }

  testWidgets('規則が当たったファイルだけなら、AIには一度も問い合わせない (受入条件8)', (tester) async {
    // Asserted as the *absence* of a call: a recording fake that is never
    // invoked is the only way to prove a file was not sent.
    var classifyCalls = 0;
    await openReview(
      tester,
      withPlan: plan(ruleMatched),
      paths: const ['subject-a/01_answers.pdf', 'subject-a/02_criteria.pdf'],
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
        listTests: () async => const [],
        classificationAvailability: () async => available(),
        planIntake:
            ({required templateId, required rootName, required files}) async =>
                plan(ruleMatched),
        classifyMaterial: ({required path}) async {
          classifyCalls++;
          throw StateError('a rule-matched file must never be classified');
        },
      ),
    );

    expect(classifyCalls, 0);
    expect(find.byKey(const Key('intake-run-classification')), findsNothing);
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('intake-import')))
          .onPressed,
      isNotNull,
    );
  });

  testWidgets('取込前に、問い合わせ件数と概算費用を出す (受入条件7)', (tester) async {
    await openReview(
      tester,
      withPlan: plan([
        ...ruleMatched,
        planned('subject-a/stray.pdf', need: ClassificationNeed.pending),
      ], pending: 1),
      paths: const [
        'subject-a/01_answers.pdf',
        'subject-a/02_criteria.pdf',
        'subject-a/stray.pdf',
      ],
      unitCost: 2.5,
    );

    expect(find.textContaining('AIに問い合わせる件数: 1件'), findsOneWidget);
    expect(find.textContaining('概算費用: 約2.50'), findsOneWidget);
  });

  testWidgets('単価が未設定なら、費用を数字で言わない', (tester) async {
    // This app cannot know what a provider charges. Printing 0 would read as
    // "free", which is a claim nobody verified.
    await openReview(
      tester,
      withPlan: plan([
        ...ruleMatched,
        planned('subject-a/stray.pdf', need: ClassificationNeed.pending),
      ], pending: 1),
      paths: const [
        'subject-a/01_answers.pdf',
        'subject-a/02_criteria.pdf',
        'subject-a/stray.pdf',
      ],
    );

    expect(find.textContaining('単価が未設定'), findsOneWidget);
  });

  testWidgets('AIの提案を確認するまでは取り込めない (受入条件6)', (tester) async {
    await openReview(
      tester,
      withPlan: plan([
        ...ruleMatched,
        planned('subject-a/stray.pdf', need: ClassificationNeed.pending),
      ], pending: 1),
      paths: const [
        'subject-a/01_answers.pdf',
        'subject-a/02_criteria.pdf',
        'subject-a/stray.pdf',
      ],
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
        listTests: () async => const [],
        classificationAvailability: () async => available(),
        planIntake:
            ({required templateId, required rootName, required files}) async =>
                plan([
                  ...ruleMatched,
                  planned(
                    'subject-a/stray.pdf',
                    need: ClassificationNeed.pending,
                  ),
                ], pending: 1),
        classifyMaterial: ({required path}) async => RoleProposalResponse(
          (builder) => builder
            ..role = MaterialRole.reference
            ..confidence = 0.9
            ..cached = false,
        ),
      ),
    );

    // Unresolved to begin with, so already unimportable.
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('intake-import')))
          .onPressed,
      isNull,
    );

    await tester.tap(find.byKey(const Key('intake-run-classification')));
    await tester.pumpAndSettle();

    // A proposal arrived -- and the batch is *still* unimportable, which is
    // the whole point. Being right is not what makes it safe.
    expect(find.byKey(const Key('intake-unconfirmed-notice')), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('intake-import')))
          .onPressed,
      isNull,
    );

    await tester.tap(
      find.byKey(const Key('intake-confirm-subject-a/stray.pdf')),
    );
    await tester.pumpAndSettle();

    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('intake-import')))
          .onPressed,
      isNotNull,
    );
  });

  testWidgets('一覧からファイルを除外できる (受入条件5)', (tester) async {
    await openReview(
      tester,
      withPlan: plan([
        ...ruleMatched,
        planned('subject-a/stray.pdf', need: ClassificationNeed.pending),
      ], pending: 1),
      paths: const [
        'subject-a/01_answers.pdf',
        'subject-a/02_criteria.pdf',
        'subject-a/stray.pdf',
      ],
    );

    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('intake-import')))
          .onPressed,
      isNull,
    );

    // Excluding the undecided file is a decision, so the batch becomes
    // importable without anything being classified.
    await tester.tap(
      find.byKey(const Key('intake-include-subject-a/stray.pdf')),
    );
    await tester.pumpAndSettle();

    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('intake-import')))
          .onPressed,
      isNotNull,
    );
  });

  testWidgets('採点基準が無ければ、新しいテストとしては登録できないと言う', (tester) async {
    await openReview(
      tester,
      withPlan: plan(
        [planned('subject-a/01_answers.pdf', role: MaterialRole.studentAnswer)],
        missing: const [MaterialRole.gradingCriteria],
      ),
      paths: const ['subject-a/01_answers.pdf'],
    );

    expect(find.byKey(const Key('intake-unmet-subject-a')), findsOneWidget);
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('intake-import')))
          .onPressed,
      isNull,
    );
  });

  testWidgets('AI判定が使えない端末では、その旨を出して手動の経路を残す', (tester) async {
    await pumpAppAt(
      tester,
      AppRoutes.intake,
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
        listTests: () async => const [],
        classificationAvailability: () async => available(yes: false),
      ),
    );
    await tester.pumpAndSettle();

    expect(find.textContaining('AIによる自動判定を使えません'), findsOneWidget);
    // Choosing a folder still works: rules need no provider at all.
    expect(
      tester
          .widget<FilledButton>(find.byKey(const Key('intake-choose-folder')))
          .onPressed,
      isNotNull,
    );
  });

  testWidgets('取込が終わっても「採点できる」とは言わず、次にやることを出す', (tester) async {
    // Issue #80 had the same failure in a different place: a screen asserting
    // something it could not know. Registering material does not make a test
    // gradable -- points and marking criteria are still missing.
    await openReview(
      tester,
      withPlan: plan(ruleMatched),
      paths: const ['subject-a/01_answers.pdf', 'subject-a/02_criteria.pdf'],
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
        listTests: () async => const [],
        classificationAvailability: () async => available(),
        planIntake:
            ({required templateId, required rootName, required files}) async =>
                plan(ruleMatched),
        createTest:
            ({
              required name,
              subject,
              required criteriaPath,
              materials = const [],
            }) async => TestResponse(
              (builder) => builder
                ..id = 'test-1'
                ..name = name
                ..status = 'draft'
                ..createdAt = DateTime.utc(2026),
            ),
        createSubmission:
            ({required testId, required filePath, studentLabel}) async =>
                SubmissionResponse(
                  (builder) => builder
                    ..id = 'sub-1'
                    ..testId = testId
                    ..state = 'ai_processed'
                    ..pageCount = 1
                    ..createdAt = DateTime.utc(2026),
                ),
      ),
    );

    await tester.tap(find.byKey(const Key('intake-import')));
    await tester.pumpAndSettle();

    expect(find.byKey(const Key('intake-next-step-notice')), findsOneWidget);
    expect(find.textContaining('配点と採点基準が必要です'), findsOneWidget);
    // Nothing here may claim the test is ready to grade. Reporting that a
    // kickoff was attempted and failed is a different thing and is allowed --
    // what is forbidden is asserting a state the app cannot know.
    expect(find.textContaining('採点できます'), findsNothing);
    expect(find.textContaining('採点を開始できます'), findsNothing);
    expect(find.textContaining('AI採点を開始しました'), findsNothing);
    // And it is not a dead end: the next action, and the undo, are one tap.
    expect(
      find.byKey(const Key('intake-open-settings-subject-a')),
      findsOneWidget,
    );
    expect(find.byKey(const Key('intake-delete-subject-a')), findsOneWidget);
  });

  testWidgets('27件目で失敗しても、その前の答案は残る', (tester) async {
    // 「成功した分は残る」: every write is its own request, so a failure costs
    // one answer rather than the batch.
    var created = 0;
    final answers = [
      for (var i = 0; i < 3; i++)
        planned(
          'subject-a/01_answers-$i.pdf',
          role: MaterialRole.studentAnswer,
        ),
    ];
    await openReview(
      tester,
      withPlan: plan([
        ...answers,
        planned(
          'subject-a/02_criteria.pdf',
          role: MaterialRole.gradingCriteria,
        ),
      ]),
      paths: const [
        'subject-a/01_answers-0.pdf',
        'subject-a/01_answers-1.pdf',
        'subject-a/01_answers-2.pdf',
        'subject-a/02_criteria.pdf',
      ],
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
        listTests: () async => const [],
        classificationAvailability: () async => available(),
        planIntake:
            ({required templateId, required rootName, required files}) async =>
                plan([
                  ...answers,
                  planned(
                    'subject-a/02_criteria.pdf',
                    role: MaterialRole.gradingCriteria,
                  ),
                ]),
        createTest:
            ({
              required name,
              subject,
              required criteriaPath,
              materials = const [],
            }) async => TestResponse(
              (builder) => builder
                ..id = 'test-1'
                ..name = name
                ..status = 'draft'
                ..createdAt = DateTime.utc(2026),
            ),
        createSubmission:
            ({required testId, required filePath, studentLabel}) async {
              created++;
              if (created == 3) {
                throw SidecarApiException(
                  SidecarErrorKind.unknown,
                  'simulated disk failure',
                );
              }
              return SubmissionResponse(
                (builder) => builder
                  ..id = 'sub-$created'
                  ..testId = testId
                  ..state = 'ai_processed'
                  ..pageCount = 1
                  ..createdAt = DateTime.utc(2026),
              );
            },
      ),
    );

    await tester.tap(find.byKey(const Key('intake-import')));
    await tester.pumpAndSettle();

    // The test itself and the two answers before the failure survive; only the
    // third is lost, and the reviewer is told.
    expect(created, 3);
    expect(find.byKey(const Key('intake-outcome-subject-a')), findsOneWidget);
    expect(find.textContaining('取り込めませんでした'), findsOneWidget);
  });

  testWidgets('取り込んだ答案のAI採点を起票する (Issue #80 の経路を落とさない)', (tester) async {
    // The screen this one replaced was the only caller of
    // `POST /submissions/{id}/jobs`. Deleting it without moving the kickoff
    // would have silently stopped grading from ever starting again.
    final graded = <String>[];
    await openReview(
      tester,
      withPlan: plan(ruleMatched),
      paths: const ['subject-a/01_answers.pdf', 'subject-a/02_criteria.pdf'],
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
        listTests: () async => const [],
        classificationAvailability: () async => available(),
        planIntake:
            ({required templateId, required rootName, required files}) async =>
                plan(ruleMatched),
        createTest:
            ({
              required name,
              subject,
              required criteriaPath,
              materials = const [],
            }) async => TestResponse(
              (builder) => builder
                ..id = 'test-1'
                ..name = name
                ..status = 'draft'
                ..createdAt = DateTime.utc(2026),
            ),
        createSubmission:
            ({required testId, required filePath, studentLabel}) async =>
                SubmissionResponse(
                  (builder) => builder
                    ..id = 'sub-1'
                    ..testId = testId
                    ..state = 'ai_processed'
                    ..pageCount = 1
                    ..createdAt = DateTime.utc(2026),
                ),
        startGrading: (submissionId) async {
          graded.add(submissionId);
          return const [];
        },
      ),
    );

    await tester.tap(find.byKey(const Key('intake-import')));
    await tester.pumpAndSettle();

    expect(graded, ['sub-1']);
    expect(find.textContaining('AI採点を開始しました'), findsOneWidget);
  });

  testWidgets('起票に失敗しても取込は成功として扱い、理由を出す', (tester) async {
    // A test registered moments ago has no confirmed question dependencies,
    // so this is the *normal* outcome right now -- not an import failure.
    await openReview(
      tester,
      withPlan: plan(ruleMatched),
      paths: const ['subject-a/01_answers.pdf', 'subject-a/02_criteria.pdf'],
      dependencies: AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
        listTests: () async => const [],
        classificationAvailability: () async => available(),
        planIntake:
            ({required templateId, required rootName, required files}) async =>
                plan(ruleMatched),
        createTest:
            ({
              required name,
              subject,
              required criteriaPath,
              materials = const [],
            }) async => TestResponse(
              (builder) => builder
                ..id = 'test-1'
                ..name = name
                ..status = 'draft'
                ..createdAt = DateTime.utc(2026),
            ),
        createSubmission:
            ({required testId, required filePath, studentLabel}) async =>
                SubmissionResponse(
                  (builder) => builder
                    ..id = 'sub-1'
                    ..testId = testId
                    ..state = 'ai_processed'
                    ..pageCount = 1
                    ..createdAt = DateTime.utc(2026),
                ),
        startGrading: (submissionId) async => throw SidecarApiException(
          SidecarErrorKind.conflict,
          'no confirmed dependency graph',
          statusCode: 409,
        ),
      ),
    );

    await tester.tap(find.byKey(const Key('intake-import')));
    await tester.pumpAndSettle();

    expect(find.textContaining('答案 1件を取り込みました'), findsOneWidget);
    expect(find.textContaining('AI採点を開始できませんでした'), findsOneWidget);
    expect(find.textContaining('AI採点を開始しました'), findsNothing);
  });
}
