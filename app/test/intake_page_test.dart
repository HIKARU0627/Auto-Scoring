import 'dart:async';

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

  IntakeRuleModel requiredRule(String pattern, MaterialRole role) =>
      IntakeRuleModel(
        (builder) => builder
          ..scope = RuleScope.file
          ..pattern = pattern
          ..role = role
          ..requirement = Requirement.required_,
      );

  /// The default template, **with its required rules**.
  ///
  /// The screen reads the required roles from here rather than from the plan:
  /// the plan reports what was missing when it was computed, and this screen
  /// lets the reviewer exclude a file afterwards (review round 4, P2-1). A
  /// template with no rules would make every requirement check vacuous.
  IntakeTemplateModel template() => IntakeTemplateModel(
    (builder) => builder
      ..id = 'serial-number-prefix'
      ..name = '連番の接頭辞 (既定)'
      ..splitChildDirectories = true
      ..rules.replace([
        requiredRule('01_*', MaterialRole.studentAnswer),
        requiredRule('02_*', MaterialRole.gradingCriteria),
      ]),
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

  /// Dependencies that import one group as a *new* test successfully.
  AppDependencies importing({
    required IntakePlanResponse withPlan,
    List<TestSummary> existingTests = const [],
    Future<SubmissionResponse> Function({
      required String testId,
      required String filePath,
      String? studentLabel,
    })?
    createSubmission,
    Future<List<SubmissionResponse>> Function(String)? listSubmissions,
    Future<List<TestMaterialResponse>> Function(String)? listMaterials,
    Future<void> Function(String)? deleteTest,
    Future<List<TestMaterialResponse>> Function(
      String, {
      required List<({MaterialRole role, String path})> materials,
    })?
    addMaterials,
    Future<AttributionProposalResponse> Function({
      required String path,
      required List<({String id, String label})> candidates,
    })?
    attributeAnswer,
  }) => AppDependencies(
    listIntakeTemplates: () async => [template()],
    intakeCost: () async => null,
    listTests: () async => existingTests,
    classificationAvailability: () async => available(),
    planIntake:
        ({required templateId, required rootName, required files}) async =>
            withPlan,
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
    addMaterials:
        addMaterials ??
        (testId, {required materials}) async => const <TestMaterialResponse>[],
    createSubmission:
        createSubmission ??
        ({required testId, required filePath, studentLabel}) async =>
            SubmissionResponse(
              (builder) => builder
                ..id = 'sub-1'
                ..testId = testId
                ..state = 'needs_review'
                ..pageCount = 1
                ..createdAt = DateTime.utc(2026),
            ),
    listSubmissions: listSubmissions ?? (_) async => const [],
    listMaterials: listMaterials ?? (_) async => const [],
    deleteTest: deleteTest ?? (_) async {},
    attributeAnswer:
        attributeAnswer ??
        ({required path, required candidates}) async =>
            AttributionProposalResponse(
              (builder) => builder
                ..testId = null
                ..confidence = 0.0,
            ),
  );

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

    expect(find.textContaining('AIに問い合わせる件数: 合計1件'), findsOneWidget);
    expect(find.textContaining('役割の判定 1件'), findsOneWidget);
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
    // 取り込めない理由は `DisabledActionReason` が `ActionRequirement` の id で
    // 出す。画面が自分の文言を持たなくなったので、キーもそちらへ移った
    // (Issue #88)。
    expect(
      find.byKey(const Key('disabled-reason-intake-proposal-unconfirmed')),
      findsOneWidget,
    );
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
    expect(find.textContaining('配点と採点基準の確定が必要です'), findsOneWidget);
    // Nothing here may claim the test is ready to grade. Reporting that a
    // kickoff was attempted and failed is a different thing and is allowed --
    // what is forbidden is asserting a state the app cannot know.
    expect(find.textContaining('採点できます'), findsNothing);
    expect(find.textContaining('採点を開始できます'), findsNothing);
    expect(find.textContaining('AI採点を開始しました'), findsNothing);
    // Issue #103 built the screen this notice used to say did not exist yet.
    // It reads 採点基準PDF (already registered by this import) directly, with
    // no profile or model-answer PDF required first, so the completion screen
    // can and does link straight to it -- the 導線 docs/intake-and-settings.md
    // §1 asks for.
    final settingsLink = tester.widget<TextButton>(
      find.byKey(const Key('intake-open-test-settings-subject-a')),
    );
    expect(settingsLink.onPressed, isNotNull);
    // The undo for what this import created is still one tap away.
    expect(find.byKey(const Key('intake-delete-subject-a')), findsOneWidget);
  });

  testWidgets('廃止済みの「入力する画面はまだありません」という文言はどこにも出ない (#111 の手口)', (tester) async {
    // Issue #103 shipped the screen this notice used to say was still being
    // built. The exact string must never resurface, on this screen or any
    // other -- pinned the same way Issue #111 pinned the retired PDF notice.
    await openReview(
      tester,
      withPlan: plan(ruleMatched),
      paths: const ['subject-a/01_answers.pdf', 'subject-a/02_criteria.pdf'],
      dependencies: importing(withPlan: plan(ruleMatched)),
    );

    await tester.tap(find.byKey(const Key('intake-import')));
    await tester.pumpAndSettle();

    expect(find.textContaining('画面はまだありません'), findsNothing);
    expect(find.textContaining('Issue #103'), findsNothing);
  });

  testWidgets('テスト設定を開くリンクは、実際にテスト設定画面へ遷移する', (tester) async {
    await openReview(
      tester,
      withPlan: plan(ruleMatched),
      paths: const ['subject-a/01_answers.pdf', 'subject-a/02_criteria.pdf'],
      dependencies: importing(withPlan: plan(ruleMatched)),
    );

    await tester.tap(find.byKey(const Key('intake-import')));
    await tester.pumpAndSettle();

    await tester.tap(
      find.byKey(const Key('intake-open-test-settings-subject-a')),
    );
    await tester.pumpAndSettle();

    // A screen that cannot fully load with this test's stub dependencies
    // still proves the route change happened without throwing -- pushing
    // somewhere is the behaviour under test, not what that screen renders.
    expect(tester.takeException(), isNull);
    expect(find.byKey(const Key('intake-import')), findsNothing);
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

  testWidgets('取込が失敗すると、見出し・要約が成功時と同じ文言にならず、失敗件数が分かる', (tester) async {
    // Every answer fails and nothing else is attached, so this group's
    // outcome carries an error with nothing imported -- a total failure,
    // not the partial one above.
    await openReview(
      tester,
      withPlan: plan(
        [planned('subject-a/01_answers.pdf', role: MaterialRole.studentAnswer)],
        missing: const [MaterialRole.gradingCriteria],
      ),
      paths: const ['subject-a/01_answers.pdf'],
      dependencies: importing(
        withPlan: plan(
          [
            planned(
              'subject-a/01_answers.pdf',
              role: MaterialRole.studentAnswer,
            ),
          ],
          missing: const [MaterialRole.gradingCriteria],
        ),
        existingTests: [
          TestSummary(
            (builder) => builder
              ..id = 'existing-1'
              ..name = '国語 第1回',
          ),
        ],
        createSubmission:
            ({required testId, required filePath, studentLabel}) async {
              throw SidecarApiException(
                SidecarErrorKind.unknown,
                'simulated failure',
              );
            },
      ),
    );

    // Bind the group to the already-registered test, same as the P1 fix
    // above -- the failure has to happen against a real target, not an
    // unassigned group the import button would refuse anyway.
    await tester.tap(find.byKey(const Key('intake-target-subject-a')));
    await tester.pumpAndSettle();
    await tester.tap(find.text('登録済み: 国語 第1回').last);
    await tester.pumpAndSettle();

    await tester.tap(find.byKey(const Key('intake-import')));
    await tester.pumpAndSettle();

    // The success wording must not appear anywhere on this screen.
    expect(find.text('取込が完了しました'), findsNothing);
    expect(find.byKey(const Key('intake-done-heading')), findsOneWidget);
    final heading = tester.widget<Text>(
      find.byKey(const Key('intake-done-heading')),
    );
    expect(heading.data, isNot('取込が完了しました'));
    expect(find.byKey(const Key('intake-failure-summary')), findsOneWidget);
    expect(find.textContaining('1件のグループで取り込みに失敗しました'), findsOneWidget);
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

  group('コードレビュー1回目で見つかった穴', () {
    testWidgets('削除は、何が消えるかを言って確認してから実行する [P1]', (tester) async {
      // The button reads "undo what I just did". Without a confirmation naming
      // the blast radius, one click could take a whole term's work.
      var deleted = 0;
      await openReview(
        tester,
        withPlan: plan(ruleMatched),
        paths: const ['subject-a/01_answers.pdf', 'subject-a/02_criteria.pdf'],
        dependencies: importing(
          withPlan: plan(ruleMatched),
          listSubmissions: (_) async => [
            for (var i = 0; i < 12; i++)
              SubmissionResponse(
                (builder) => builder
                  ..id = 'sub-$i'
                  ..testId = 'test-1'
                  ..state = 'needs_review'
                  ..pageCount = 1
                  ..createdAt = DateTime.utc(2026),
              ),
          ],
          listMaterials: (_) async => [
            TestMaterialResponse(
              (builder) => builder
                ..id = 'mat-1'
                ..testId = 'test-1'
                ..role = MaterialRole.gradingCriteria
                ..sha256 = digest
                ..sizeBytes = 1
                ..createdAt = DateTime.utc(2026),
            ),
          ],
          deleteTest: (_) async => deleted++,
        ),
      );
      await tester.tap(find.byKey(const Key('intake-import')));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('intake-delete-subject-a')));
      await tester.pumpAndSettle();

      // Nothing has been deleted yet, and the dialog says what would be.
      expect(deleted, 0);
      expect(find.byKey(const Key('intake-delete-confirm')), findsOneWidget);
      expect(find.textContaining('答案 12件'), findsOneWidget);
      // Inside the dialog specifically -- the outcome card behind it also
      // mentions a material count.
      expect(
        find.descendant(
          of: find.byKey(const Key('intake-delete-confirm')),
          matching: find.textContaining('資料 1件'),
        ),
        findsOneWidget,
      );
      expect(find.textContaining('元に戻せません'), findsOneWidget);

      // Backing out deletes nothing.
      await tester.tap(find.byKey(const Key('intake-delete-cancel')));
      await tester.pumpAndSettle();
      expect(deleted, 0);
      expect(find.byKey(const Key('intake-delete-subject-a')), findsOneWidget);

      await tester.tap(find.byKey(const Key('intake-delete-subject-a')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-delete-confirmed')));
      await tester.pumpAndSettle();
      expect(deleted, 1);
    });

    testWidgets('登録済みテストに足しただけのときは、削除を出さない [P1]', (tester) async {
      // Deleting there would throw away every previous week's answers and
      // grading -- from a button pressed meaning "undo this week's import".
      await openReview(
        tester,
        withPlan: plan(
          [
            planned(
              'subject-a/01_answers.pdf',
              role: MaterialRole.studentAnswer,
            ),
          ],
          missing: const [MaterialRole.gradingCriteria],
        ),
        paths: const ['subject-a/01_answers.pdf'],
        dependencies: importing(
          withPlan: plan(
            [
              planned(
                'subject-a/01_answers.pdf',
                role: MaterialRole.studentAnswer,
              ),
            ],
            missing: const [MaterialRole.gradingCriteria],
          ),
          existingTests: [
            TestSummary(
              (builder) => builder
                ..id = 'existing-1'
                ..name = '国語 第1回',
            ),
          ],
        ),
      );

      // Bind the group to the already-registered test.
      await tester.tap(find.byKey(const Key('intake-target-subject-a')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('登録済み: 国語 第1回').last);
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('intake-import')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('intake-delete-subject-a')), findsNothing);
    });

    testWidgets('一部失敗でも、取り込めた分と失敗したファイル名を出す', (tester) async {
      var created = 0;
      final answers = [
        for (var i = 0; i < 3; i++)
          planned(
            'subject-a/01_answers-$i.pdf',
            role: MaterialRole.studentAnswer,
          ),
      ];
      final withCriteria = plan([
        ...answers,
        planned(
          'subject-a/02_criteria.pdf',
          role: MaterialRole.gradingCriteria,
        ),
      ]);
      await openReview(
        tester,
        withPlan: withCriteria,
        paths: const [
          'subject-a/01_answers-0.pdf',
          'subject-a/01_answers-1.pdf',
          'subject-a/01_answers-2.pdf',
          'subject-a/02_criteria.pdf',
        ],
        dependencies: importing(
          withPlan: withCriteria,
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
                    ..state = 'needs_review'
                    ..pageCount = 1
                    ..createdAt = DateTime.utc(2026),
                );
              },
        ),
      );

      await tester.tap(find.byKey(const Key('intake-import')));
      await tester.pumpAndSettle();

      // The two that landed are reported, not hidden behind the one that did
      // not -- otherwise the reviewer re-imports all three.
      expect(
        find.byKey(const Key('intake-imported-subject-a')),
        findsOneWidget,
      );
      expect(find.textContaining('答案 2件を取り込みました'), findsOneWidget);
      expect(find.textContaining('一部を取り込めませんでした'), findsOneWidget);
      // Named, so the reviewer can find it.
      expect(find.textContaining('失敗したファイル: 01_answers-2.pdf'), findsOneWidget);
    });

    testWidgets('バッチごとにテスト一覧を取り直す（さっき作ったテストが候補に出る）', (tester) async {
      // The ordinary sequence is "import the criteria folder, then the answers
      // folder". The test just created has to be offerable as a target.
      var listCalls = 0;
      await pumpAppAt(
        tester,
        AppRoutes.intake,
        dependencies: AppDependencies(
          listIntakeTemplates: () async => [template()],
          intakeCost: () async => null,
          classificationAvailability: () async => available(),
          listTests: () async {
            listCalls++;
            return listCalls == 1
                ? const []
                : [
                    TestSummary(
                      (builder) => builder
                        ..id = 'test-1'
                        ..name = 'さっき作ったテスト',
                    ),
                  ];
          },
          planIntake:
              ({
                required templateId,
                required rootName,
                required files,
              }) async => plan(ruleMatched),
        ),
        overrides: [
          chooseFolderProvider.overrideWithValue(() async => '/tmp/batch'),
          scanFolderProvider.overrideWithValue(
            (_) async => folder(const [
              'subject-a/01_answers.pdf',
              'subject-a/02_criteria.pdf',
            ]),
          ),
        ],
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-choose-folder')));
      await tester.pumpAndSettle();

      expect(listCalls, greaterThan(1));
      expect(find.byKey(const Key('intake-narrow-test-1')), findsOneWidget);
    });

    testWidgets('提案をまとめて確認する導線がある', (tester) async {
      final withStray = plan([
        ...ruleMatched,
        planned('subject-a/stray.pdf', need: ClassificationNeed.pending),
      ], pending: 1);
      await openReview(
        tester,
        withPlan: withStray,
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
              ({
                required templateId,
                required rootName,
                required files,
              }) async => withStray,
          classifyMaterial: ({required path}) async => RoleProposalResponse(
            (builder) => builder
              ..role = MaterialRole.reference
              ..confidence = 0.9
              ..cached = false,
          ),
        ),
      );

      await tester.tap(find.byKey(const Key('intake-run-classification')));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('intake-confirm-all')));
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNotNull,
      );
    });

    testWidgets('キャッシュ済みの提案を取りに行く（40枚がまた手動に戻らない）', (tester) async {
      // Re-selecting a folder returns `cached` for content the sidecar has
      // already classified. Treating that as "nothing to do" left every row
      // undecided and threw away answers already paid for.
      var classifyCalls = 0;
      final cachedPlan = plan([
        ...ruleMatched,
        planned('subject-a/stray.pdf', need: ClassificationNeed.cached),
      ]);
      await openReview(
        tester,
        withPlan: cachedPlan,
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
              ({
                required templateId,
                required rootName,
                required files,
              }) async => cachedPlan,
          classifyMaterial: ({required path}) async {
            classifyCalls++;
            return RoleProposalResponse(
              (builder) => builder
                ..role = MaterialRole.annotationSample
                ..confidence = 0.0
                ..cached = true,
            );
          },
        ),
      );

      // A separate, free control -- and the paid one is not offered at all,
      // because nothing here would cost anything.
      expect(find.textContaining('前回の判定を取得する (1件・無料)'), findsOneWidget);
      expect(find.byKey(const Key('intake-run-classification')), findsNothing);
      expect(find.textContaining('役割の判定 0件'), findsOneWidget);

      await tester.tap(find.byKey(const Key('intake-fetch-cached')));
      await tester.pumpAndSettle();

      expect(classifyCalls, 1);
      // The cached answer arrives as a proposal that still needs confirming.
      expect(
        find.byKey(const Key('disabled-reason-intake-proposal-unconfirmed')),
        findsOneWidget,
      );
      await tester.tap(find.byKey(const Key('intake-confirm-all')));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNotNull,
      );
    });

    testWidgets('「判定できなかった」に二度課金しない', (tester) async {
      var classifyCalls = 0;
      final withStray = plan([
        ...ruleMatched,
        planned('subject-a/stray.pdf', need: ClassificationNeed.pending),
      ], pending: 1);
      await openReview(
        tester,
        withPlan: withStray,
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
              ({
                required templateId,
                required rootName,
                required files,
              }) async => withStray,
          classifyMaterial: ({required path}) async {
            classifyCalls++;
            return RoleProposalResponse(
              (builder) => builder
                ..role = null
                ..confidence = 0.0
                ..cached = false,
            );
          },
        ),
      );

      await tester.tap(find.byKey(const Key('intake-run-classification')));
      await tester.pumpAndSettle();
      expect(classifyCalls, 1);

      // The file is still undecided -- but asking again would buy the same
      // reply at the same price, so the run is no longer offered for it.
      expect(find.byKey(const Key('intake-run-classification')), findsNothing);
      expect(classifyCalls, 1);
    });

    testWidgets('候補を絞り直しても、振り分け済みの答案で落ちない', (tester) async {
      final answersOnly = plan(
        [planned('subject-a/01_answers.pdf', role: MaterialRole.studentAnswer)],
        missing: const [MaterialRole.gradingCriteria],
      );
      await openReview(
        tester,
        withPlan: answersOnly,
        paths: const ['subject-a/01_answers.pdf'],
        dependencies: importing(
          withPlan: answersOnly,
          existingTests: [
            TestSummary(
              (builder) => builder
                ..id = 'test-a'
                ..name = '国語',
            ),
            TestSummary(
              (builder) => builder
                ..id = 'test-b'
                ..name = '数学',
            ),
          ],
        ),
      );

      await tester.tap(find.byKey(const Key('intake-target-subject-a')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('答案ごとに登録済みのテストへ振り分ける').last);
      await tester.pumpAndSettle();

      // The estimate now counts the attribution call this routing would need
      // -- role classification is 0 here because a rule matched the name, and
      // showing only that number would have said "free" right before spending.
      expect(find.textContaining('答案の振り分け 1件'), findsOneWidget);
      expect(find.textContaining('AIに問い合わせる件数: 合計1件'), findsOneWidget);

      // Route the answer to 国語...
      await tester.tap(
        find.byKey(const Key('intake-answer-target-subject-a/01_answers.pdf')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.text('国語').last);
      await tester.pumpAndSettle();

      // ...then narrow the candidates to 数学 only. The routing to 国語 has to
      // be dropped, not left pointing at a value the control no longer offers.
      await tester.tap(find.byKey(const Key('intake-narrow-test-b')));
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNull,
      );
    });
  });

  group('コードレビュー2回目で見つかった穴', () {
    /// A group of answers-only files bound to per-answer routing, with two
    /// registered tests to choose between.
    Future<void> openPerAnswer(
      WidgetTester tester, {
      required AppDependencies dependencies,
    }) async {
      final answersOnly = plan(
        [planned('subject-a/01_answers.pdf', role: MaterialRole.studentAnswer)],
        missing: const [MaterialRole.gradingCriteria],
      );
      await openReview(
        tester,
        withPlan: answersOnly,
        paths: const ['subject-a/01_answers.pdf'],
        dependencies: dependencies,
      );
      await tester.tap(find.byKey(const Key('intake-target-subject-a')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('答案ごとに登録済みのテストへ振り分ける').last);
      await tester.pumpAndSettle();
    }

    AppDependencies perAnswerDeps({
      String? attributesTo = 'test-a',
      List<TestSummary>? tests,
    }) {
      final answersOnly = plan(
        [planned('subject-a/01_answers.pdf', role: MaterialRole.studentAnswer)],
        missing: const [MaterialRole.gradingCriteria],
      );
      return AppDependencies(
        listIntakeTemplates: () async => [template()],
        intakeCost: () async => null,
        classificationAvailability: () async => available(),
        listTests: () async =>
            tests ??
            [
              TestSummary(
                (builder) => builder
                  ..id = 'test-a'
                  ..name = '国語',
              ),
              TestSummary(
                (builder) => builder
                  ..id = 'test-b'
                  ..name = '数学',
              ),
            ],
        planIntake:
            ({required templateId, required rootName, required files}) async =>
                answersOnly,
        attributeAnswer: ({required path, required candidates}) async =>
            AttributionProposalResponse(
              (builder) => builder
                ..testId = attributesTo
                ..confidence = 0.8,
            ),
      );
    }

    testWidgets('AIの振り分けは提案として出て、確認するまで取り込めない [P1]', (tester) async {
      await openPerAnswer(tester, dependencies: perAnswerDeps());

      await tester.ensureVisible(
        find.byKey(const Key('intake-attribute-subject-a')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-attribute-subject-a')));
      await tester.pumpAndSettle();

      // The proposal is shown as a proposal, and the batch is still blocked.
      expect(find.textContaining('AI提案: 国語'), findsOneWidget);
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNull,
      );

      await tester.tap(
        find.byKey(const Key('intake-confirm-target-subject-a/01_answers.pdf')),
      );
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNotNull,
      );
    });

    testWidgets('振り分けの提案も一括確認で確定できる', (tester) async {
      await openPerAnswer(tester, dependencies: perAnswerDeps());
      await tester.ensureVisible(
        find.byKey(const Key('intake-attribute-subject-a')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-attribute-subject-a')));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('intake-confirm-all')));
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNotNull,
      );
    });

    testWidgets('「判定できなかった」振り分けは、一括確認でも確定しない', (tester) async {
      await openPerAnswer(
        tester,
        dependencies: perAnswerDeps(attributesTo: null),
      );
      await tester.ensureVisible(
        find.byKey(const Key('intake-attribute-subject-a')),
      );
      await tester.pumpAndSettle();
      await tester.ensureVisible(
        find.byKey(const Key('intake-attribute-subject-a')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-attribute-subject-a')));
      await tester.pumpAndSettle();

      // Nothing was proposed, so there is nothing to bulk-confirm -- the
      // control is not offered at all. "Could not tell" must never become
      // "the reviewer approved it".
      expect(find.byKey(const Key('intake-confirm-all')), findsNothing);
      expect(find.textContaining('AI提案'), findsNothing);
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNull,
      );
    });

    testWidgets('候補を1件に絞ったときは提案ではなく確定（AIを呼ばない）', (tester) async {
      var attributeCalls = 0;
      final answersOnly = plan(
        [planned('subject-a/01_answers.pdf', role: MaterialRole.studentAnswer)],
        missing: const [MaterialRole.gradingCriteria],
      );
      await openReview(
        tester,
        withPlan: answersOnly,
        paths: const ['subject-a/01_answers.pdf'],
        dependencies: AppDependencies(
          listIntakeTemplates: () async => [template()],
          intakeCost: () async => null,
          classificationAvailability: () async => available(),
          listTests: () async => [
            TestSummary(
              (builder) => builder
                ..id = 'test-a'
                ..name = '国語',
            ),
            TestSummary(
              (builder) => builder
                ..id = 'test-b'
                ..name = '数学',
            ),
          ],
          planIntake:
              ({
                required templateId,
                required rootName,
                required files,
              }) async => answersOnly,
          attributeAnswer: ({required path, required candidates}) async {
            attributeCalls++;
            throw StateError('must not ask with a single candidate');
          },
        ),
      );
      await tester.tap(find.byKey(const Key('intake-target-subject-a')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('答案ごとに登録済みのテストへ振り分ける').last);
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('intake-narrow-test-a')));
      await tester.pumpAndSettle();
      await tester.ensureVisible(
        find.byKey(const Key('intake-attribute-subject-a')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-attribute-subject-a')));
      await tester.pumpAndSettle();

      // Narrowing to one test *is* the reviewer's answer -- nothing was
      // guessed, so nothing needs confirming and nothing was spent.
      expect(attributeCalls, 0);
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNotNull,
      );
    });

    testWidgets('削除の件数を取れなかったときは、件数を断定しない', (tester) async {
      await openReview(
        tester,
        withPlan: plan(ruleMatched),
        paths: const ['subject-a/01_answers.pdf', 'subject-a/02_criteria.pdf'],
        dependencies: importing(
          withPlan: plan(ruleMatched),
          listSubmissions: (_) async => throw SidecarApiException(
            SidecarErrorKind.unavailable,
            'sidecar is not connected',
          ),
        ),
      );
      await tester.tap(find.byKey(const Key('intake-import')));
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-delete-subject-a')));
      await tester.pumpAndSettle();

      // No number is asserted, and the reviewer is told why.
      expect(find.textContaining('確認できませんでした'), findsOneWidget);
      expect(find.textContaining('答案 0件'), findsNothing);
    });

    testWidgets('キャッシュ取得は provider が無くても押せる（無料なので）', (tester) async {
      var classifyCalls = 0;
      final cachedPlan = plan([
        ...ruleMatched,
        planned('subject-a/stray.pdf', need: ClassificationNeed.cached),
      ]);
      await openReview(
        tester,
        withPlan: cachedPlan,
        paths: const [
          'subject-a/01_answers.pdf',
          'subject-a/02_criteria.pdf',
          'subject-a/stray.pdf',
        ],
        dependencies: AppDependencies(
          listIntakeTemplates: () async => [template()],
          intakeCost: () async => null,
          listTests: () async => const [],
          // No provider on this host at all.
          classificationAvailability: () async => available(yes: false),
          planIntake:
              ({
                required templateId,
                required rootName,
                required files,
              }) async => cachedPlan,
          classifyMaterial: ({required path}) async {
            classifyCalls++;
            return RoleProposalResponse(
              (builder) => builder
                ..role = MaterialRole.annotationSample
                ..confidence = 0.0
                ..cached = true,
            );
          },
        ),
      );

      // The paid button is gone; the free one is not.
      expect(find.byKey(const Key('intake-run-classification')), findsNothing);
      expect(find.byKey(const Key('intake-fetch-cached')), findsOneWidget);

      await tester.tap(find.byKey(const Key('intake-fetch-cached')));
      await tester.pumpAndSettle();

      expect(classifyCalls, 1);
      await tester.tap(find.byKey(const Key('intake-confirm-all')));
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNotNull,
      );
    });
  });

  group('送信内容の明示（業務ルール §2 (2)）', () {
    testWidgets('振り分けを実行する前に、ページ全体を送ることを言う', (tester) async {
      // Attribution reads the answer sheet's header, so the whole page goes.
      // The reviewer is told before it happens, in the same place as the cost.
      final answersOnly = plan(
        [planned('subject-a/01_answers.pdf', role: MaterialRole.studentAnswer)],
        missing: const [MaterialRole.gradingCriteria],
      );
      await openReview(
        tester,
        withPlan: answersOnly,
        paths: const ['subject-a/01_answers.pdf'],
        dependencies: importing(
          withPlan: answersOnly,
          existingTests: [
            TestSummary(
              (builder) => builder
                ..id = 'test-a'
                ..name = '国語',
            ),
            TestSummary(
              (builder) => builder
                ..id = 'test-b'
                ..name = '数学',
            ),
          ],
        ),
      );
      await tester.tap(find.byKey(const Key('intake-target-subject-a')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('答案ごとに登録済みのテストへ振り分ける').last);
      await tester.pumpAndSettle();

      expect(
        find.byKey(const Key('intake-attribution-notice')),
        findsOneWidget,
      );
      // Both the pre-flight notice and the narrowing hint mention it, which is
      // the point: it is said where the cost is said, and again where the way
      // to avoid it is offered.
      expect(find.textContaining('ページ全体'), findsNWidgets(2));
    });

    testWidgets('候補を1件に絞ると、送信の予告も消える', (tester) async {
      // Narrowing to one test is the escape hatch: nothing is asked, so
      // nothing is sent. The screen must stop warning about a send that will
      // not happen.
      final answersOnly = plan(
        [planned('subject-a/01_answers.pdf', role: MaterialRole.studentAnswer)],
        missing: const [MaterialRole.gradingCriteria],
      );
      await openReview(
        tester,
        withPlan: answersOnly,
        paths: const ['subject-a/01_answers.pdf'],
        dependencies: importing(
          withPlan: answersOnly,
          existingTests: [
            TestSummary(
              (builder) => builder
                ..id = 'test-a'
                ..name = '国語',
            ),
            TestSummary(
              (builder) => builder
                ..id = 'test-b'
                ..name = '数学',
            ),
          ],
        ),
      );
      await tester.tap(find.byKey(const Key('intake-target-subject-a')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('答案ごとに登録済みのテストへ振り分ける').last);
      await tester.pumpAndSettle();
      expect(
        find.byKey(const Key('intake-attribution-notice')),
        findsOneWidget,
      );

      await tester.tap(find.byKey(const Key('intake-narrow-test-a')));
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('intake-attribution-notice')), findsNothing);
      expect(find.textContaining('AIに問い合わせる件数: 合計0件'), findsOneWidget);
    });

    testWidgets('絞り込みが送信を避ける手段であることを案内する', (tester) async {
      await openReview(
        tester,
        withPlan: plan(ruleMatched),
        paths: const ['subject-a/01_answers.pdf', 'subject-a/02_criteria.pdf'],
        dependencies: importing(
          withPlan: plan(ruleMatched),
          existingTests: [
            TestSummary(
              (builder) => builder
                ..id = 'test-a'
                ..name = '国語',
            ),
          ],
        ),
      );

      expect(find.byKey(const Key('intake-narrowing-benefit')), findsOneWidget);
      expect(find.textContaining('ページ全体も送りません'), findsOneWidget);
    });
  });

  group('コードレビュー3回目で見つかった穴', () {
    IntakePlanResponse answersOnlyPlan() => plan(
      [
        planned('subject-a/01_answers.pdf', role: MaterialRole.studentAnswer),
        planned('subject-a/01_answers-2.pdf', role: MaterialRole.studentAnswer),
      ],
      missing: const [MaterialRole.gradingCriteria],
    );

    Future<void> openPerAnswerWith(
      WidgetTester tester, {
      required AppDependencies dependencies,
    }) async {
      await openReview(
        tester,
        withPlan: answersOnlyPlan(),
        paths: const ['subject-a/01_answers.pdf', 'subject-a/01_answers-2.pdf'],
        dependencies: dependencies,
      );
      await tester.tap(find.byKey(const Key('intake-target-subject-a')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('答案ごとに登録済みのテストへ振り分ける').last);
      await tester.pumpAndSettle();
    }

    testWidgets('登録済みテストが1件でも、選ばないうちは振り分けない [P1-1]', (tester) async {
      // "Only one test is registered" is what every first-time user has. It is
      // not the reviewer saying the answers belong to it.
      await openPerAnswerWith(
        tester,
        dependencies: importing(
          withPlan: answersOnlyPlan(),
          existingTests: [
            TestSummary(
              (builder) => builder
                ..id = 'test-a'
                ..name = '国語',
            ),
          ],
        ),
      );

      // The control is offered but refuses, and says what to do instead.
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('intake-attribute-subject-a')),
            )
            .onPressed,
        isNull,
      );
      expect(find.text('振り分け先を選んでください'), findsOneWidget);
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNull,
      );

      // Choosing it explicitly is what unlocks the routing.
      await tester.tap(find.byKey(const Key('intake-narrow-test-a')));
      await tester.pumpAndSettle();
      expect(find.textContaining('すべての答案を「国語」に振り分ける'), findsOneWidget);
      await tester.ensureVisible(
        find.byKey(const Key('intake-attribute-subject-a')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-attribute-subject-a')));
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNotNull,
      );
    });

    testWidgets('判定中に候補を変えても、画面が固まらない [P1-2]', (tester) async {
      // Discarding a stale response and leaving the screen "running" are two
      // different things. The round-2 staleness fix conflated them and left
      // every button disabled with no way back.
      final gate = Completer<void>();
      await openPerAnswerWith(
        tester,
        dependencies: importing(
          withPlan: answersOnlyPlan(),
          existingTests: [
            TestSummary(
              (builder) => builder
                ..id = 'test-a'
                ..name = '国語',
            ),
            TestSummary(
              (builder) => builder
                ..id = 'test-b'
                ..name = '数学',
            ),
          ],
          attributeAnswer: ({required path, required candidates}) async {
            await gate.future;
            return AttributionProposalResponse(
              (builder) => builder
                ..testId = 'test-a'
                ..confidence = 0.8,
            );
          },
        ),
      );

      await tester.ensureVisible(
        find.byKey(const Key('intake-attribute-subject-a')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-attribute-subject-a')));
      await tester.pump();

      // Change the candidates while the request is in flight.
      await tester.tap(find.byKey(const Key('intake-narrow-test-b')));
      await tester.pump();

      gate.complete();
      await tester.pumpAndSettle();

      // The stale answer was dropped -- and the screen came back.
      expect(
        tester
            .widget<FilledButton>(
              find.byKey(const Key('intake-attribute-subject-a')),
            )
            .onPressed,
        isNotNull,
        reason: '実行中フラグが下りていないと、以後どのボタンも押せない',
      );
    });

    testWidgets('単価を空にして戻っても落ちない [P1-3]', (tester) async {
      // `copyWith(unitCost: null)` used to mean "keep the old price", so the
      // estimate held a figure the screen thought did not exist.
      double? cost = 2.5;
      final withStray = plan([
        ...ruleMatched,
        planned('subject-a/stray.pdf', need: ClassificationNeed.pending),
      ], pending: 1);
      await openReview(
        tester,
        withPlan: withStray,
        paths: const [
          'subject-a/01_answers.pdf',
          'subject-a/02_criteria.pdf',
          'subject-a/stray.pdf',
        ],
        dependencies: AppDependencies(
          listIntakeTemplates: () async => [template()],
          intakeCost: () async => cost,
          listTests: () async => const [],
          classificationAvailability: () async => available(),
          planIntake:
              ({
                required templateId,
                required rootName,
                required files,
              }) async => withStray,
        ),
      );
      expect(find.textContaining('概算費用: 約2.50'), findsOneWidget);

      // The reviewer clears the price in settings and comes back.
      cost = null;
      await tester.tap(find.byKey(const Key('intake-open-settings')));
      await tester.pumpAndSettle();
      final navigator = tester.state<NavigatorState>(find.byType(Navigator));
      navigator.pop();
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.textContaining('単価が未設定'), findsOneWidget);
    });

    testWidgets('AIが外したあとでも、1件に絞れば一括で振り分けられる [P2]', (tester) async {
      // The re-charge guard must not block the reviewer's own decision. Forty
      // answers the classifier could not place, then one narrowing click --
      // not forty dropdown operations.
      await openPerAnswerWith(
        tester,
        dependencies: importing(
          withPlan: answersOnlyPlan(),
          existingTests: [
            TestSummary(
              (builder) => builder
                ..id = 'test-a'
                ..name = '国語',
            ),
            TestSummary(
              (builder) => builder
                ..id = 'test-b'
                ..name = '数学',
            ),
          ],
          // The classifier cannot tell, for either answer.
          attributeAnswer: ({required path, required candidates}) async =>
              AttributionProposalResponse(
                (builder) => builder
                  ..testId = null
                  ..confidence = 0.0,
              ),
        ),
      );

      await tester.ensureVisible(
        find.byKey(const Key('intake-attribute-subject-a')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-attribute-subject-a')));
      await tester.pumpAndSettle();

      // Both answers are still unrouted, and both are marked as asked.
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNull,
      );

      await tester.tap(find.byKey(const Key('intake-narrow-test-a')));
      await tester.pumpAndSettle();
      await tester.ensureVisible(
        find.byKey(const Key('intake-attribute-subject-a')),
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-attribute-subject-a')));
      await tester.pumpAndSettle();

      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNotNull,
        reason: '再課金防止のフィルタが人の操作にまで効いていると、ここで止まる',
      );
    });
  });

  group('コードレビュー4回目で見つかった穴', () {
    testWidgets('幅390pxでも取込ボタンが画面内にある [P2-2]', (tester) async {
      // A phone-width window. `Row` neither shrinks nor wraps, so the import
      // button sat 80px off-screen with no horizontal scroll to reach it.
      tester.view.physicalSize = const Size(390, 844);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.resetPhysicalSize);
      addTearDown(tester.view.resetDevicePixelRatio);

      final withStray = plan([
        ...ruleMatched,
        planned('subject-a/stray.pdf', need: ClassificationNeed.pending),
      ], pending: 1);
      await openReview(
        tester,
        withPlan: withStray,
        paths: const [
          'subject-a/01_answers.pdf',
          'subject-a/02_criteria.pdf',
          'subject-a/stray.pdf',
        ],
        dependencies: importing(withPlan: withStray),
      );

      // Both controls are rendered, and both are inside the window.
      expect(
        find.byKey(const Key('intake-run-classification')),
        findsOneWidget,
      );
      final importRect = tester.getRect(find.byKey(const Key('intake-import')));
      expect(
        importRect.right,
        lessThanOrEqualTo(390.0),
        reason: '取込ボタンが画面外に出ている',
      );
      expect(importRect.left, greaterThanOrEqualTo(0.0));
      // And nothing overflowed while laying it out.
      expect(tester.takeException(), isNull);
    });

    testWidgets('確認画面で採点基準を除外すると、取り込めなくなる [P2-1]', (tester) async {
      // The plan reported nothing missing, because at plan time nothing was.
      // Excluding it here has to be noticed on this screen -- not discovered
      // by the import failing on the completion screen, which cannot fix it.
      await openReview(
        tester,
        withPlan: plan(ruleMatched),
        paths: const ['subject-a/01_answers.pdf', 'subject-a/02_criteria.pdf'],
        dependencies: importing(withPlan: plan(ruleMatched)),
      );
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNotNull,
      );

      await tester.tap(
        find.byKey(const Key('intake-include-subject-a/02_criteria.pdf')),
      );
      await tester.pumpAndSettle();

      expect(find.byKey(const Key('intake-unmet-subject-a')), findsOneWidget);
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNull,
      );
    });

    testWidgets('絞り込んだテストが消えても落ちない（同型の探索で発見）', (tester) async {
      // `_narrowedTestIds` is a selection that outlives the list it points
      // into: the registered tests are re-read on returning from settings and
      // at the start of every batch. With the group routing answers
      // individually, a chosen test that has since been deleted used to reach
      // `_attributionCandidates.single` on an empty list.
      var listCalls = 0;
      final answersOnly = plan([
        planned('subject-a/01_answers.pdf', role: MaterialRole.studentAnswer),
      ]);
      await pumpAppAt(
        tester,
        AppRoutes.intake,
        dependencies: AppDependencies(
          listIntakeTemplates: () async => [template()],
          intakeCost: () async => null,
          classificationAvailability: () async => available(),
          listTests: () async {
            listCalls++;
            // Gone once the settings round-trip re-reads the list.
            return listCalls >= 3
                ? const <TestSummary>[]
                : [
                    TestSummary(
                      (builder) => builder
                        ..id = 'test-a'
                        ..name = '国語',
                    ),
                  ];
          },
          planIntake:
              ({
                required templateId,
                required rootName,
                required files,
              }) async => answersOnly,
        ),
        overrides: [
          chooseFolderProvider.overrideWithValue(() async => '/tmp/batch'),
          scanFolderProvider.overrideWithValue(
            (_) async => folder(const ['subject-a/01_answers.pdf']),
          ),
        ],
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-choose-folder')));
      await tester.pumpAndSettle();

      // Route answers individually, and narrow to the one registered test.
      await tester.tap(find.byKey(const Key('intake-target-subject-a')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('答案ごとに登録済みのテストへ振り分ける').last);
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-narrow-test-a')));
      await tester.pumpAndSettle();
      expect(find.textContaining('すべての答案を「国語」に振り分ける'), findsOneWidget);

      // Going to settings and back re-reads the list; the chosen test is gone.
      await tester.tap(find.byKey(const Key('intake-open-settings')));
      await tester.pumpAndSettle();
      tester.state<NavigatorState>(find.byType(Navigator)).pop();
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(find.byKey(const Key('intake-narrow-test-a')), findsNothing);
      // The group's target is reset rather than left pointing at something
      // that no longer exists, so the batch cannot be imported until the
      // reviewer chooses again.
      expect(find.byKey(const Key('intake-attribute-subject-a')), findsNothing);
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNull,
      );
    });

    testWidgets('紐づけ先のテストが消えたら、取り込み先を選び直させる', (tester) async {
      // The other half of the same shape: a group bound to a registered test
      // that has since gone used to still report itself ready, and failed at
      // import time with a dead id -- on the completion screen, which cannot
      // fix it.
      var listCalls = 0;
      final answersOnly = plan([
        planned('subject-a/01_answers.pdf', role: MaterialRole.studentAnswer),
      ]);
      await pumpAppAt(
        tester,
        AppRoutes.intake,
        dependencies: AppDependencies(
          listIntakeTemplates: () async => [template()],
          intakeCost: () async => null,
          classificationAvailability: () async => available(),
          listTests: () async {
            listCalls++;
            return listCalls >= 3
                ? [
                    TestSummary(
                      (builder) => builder
                        ..id = 'test-b'
                        ..name = '数学',
                    ),
                  ]
                : [
                    TestSummary(
                      (builder) => builder
                        ..id = 'test-a'
                        ..name = '国語',
                    ),
                  ];
          },
          planIntake:
              ({
                required templateId,
                required rootName,
                required files,
              }) async => answersOnly,
        ),
        overrides: [
          chooseFolderProvider.overrideWithValue(() async => '/tmp/batch'),
          scanFolderProvider.overrideWithValue(
            (_) async => folder(const ['subject-a/01_answers.pdf']),
          ),
        ],
      );
      await tester.pumpAndSettle();
      await tester.tap(find.byKey(const Key('intake-choose-folder')));
      await tester.pumpAndSettle();

      await tester.tap(find.byKey(const Key('intake-target-subject-a')));
      await tester.pumpAndSettle();
      await tester.tap(find.text('登録済み: 国語').last);
      await tester.pumpAndSettle();
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNotNull,
      );

      await tester.tap(find.byKey(const Key('intake-open-settings')));
      await tester.pumpAndSettle();
      tester.state<NavigatorState>(find.byType(Navigator)).pop();
      await tester.pumpAndSettle();

      expect(tester.takeException(), isNull);
      expect(
        tester
            .widget<FilledButton>(find.byKey(const Key('intake-import')))
            .onPressed,
        isNull,
        reason: '消えたテストに紐づいたまま取り込めてはいけない',
      );
    });
  });
}
