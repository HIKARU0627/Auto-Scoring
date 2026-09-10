import 'package:flutter_test/flutter_test.dart';

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/folder_scan.dart';
import 'package:auto_scoring_app/core/intake_review.dart';

/// The confirmation step's rules, tested as state rather than through a screen
/// (Issue #101).
///
/// The rule that matters is acceptance criterion 6: **an AI proposal the
/// reviewer has not looked at makes the batch unimportable.** Asserting that
/// here rather than only by checking whether a button is greyed out means the
/// rule survives any later redesign of the screen.
void main() {
  IntakeFileState file({
    String path = 'subject-a/01_answers.pdf',
    MaterialRole? ruleRole,
    MaterialRole? proposedRole,
    bool proposalConfirmed = false,
    MaterialRole? humanRole,
    bool excluded = false,
    bool needsClassification = false,
    bool cached = false,
    String? answerTestId,
    String? proposedAnswerTestId,
    bool attributionAttempted = false,
  }) => IntakeFileState(
    relativePath: path,
    absolutePath: '/tmp/$path',
    sha256: '0' * 64,
    sizeBytes: 1,
    ruleRole: ruleRole,
    needsClassification: needsClassification,
    cachedClassification: cached,
    proposedRole: proposedRole,
    proposalConfirmed: proposalConfirmed,
    humanRole: humanRole,
    excluded: excluded,
    answerTestId: answerTestId,
    proposedAnswerTestId: proposedAnswerTestId,
    attributionAttempted: attributionAttempted,
  );

  IntakeGroupState buildGroup(
    List<IntakeFileState> files, {
    IntakeTargetKind kind = IntakeTargetKind.create,
    String? testId,
    List<MaterialRole> missing = const [],
    String name = '国語',
  }) => IntakeGroupState(
    key: 'subject-a',
    name: name,
    files: files,
    requiredRoles: missing,
    targetKind: kind,
    targetTestId: testId,
  );

  IntakeReviewState state(List<IntakeGroupState> groups, {double? unitCost}) =>
      IntakeReviewState(groups: groups, unitCost: unitCost);

  final complete = [
    file(ruleRole: MaterialRole.studentAnswer),
    file(
      path: 'subject-a/02_criteria.pdf',
      ruleRole: MaterialRole.gradingCriteria,
    ),
  ];

  group('確認していないAI提案がある間は取り込めない (受入条件6)', () {
    test('未確認の提案が1件でもあれば取り込めない', () {
      final review = state([
        buildGroup([
          ...complete,
          file(
            path: 'subject-a/stray.pdf',
            proposedRole: MaterialRole.reference,
          ),
        ]),
      ]);

      expect(review.unconfirmedProposals, hasLength(1));
      expect(review.canImport, isFalse);
    });

    test('提案を確認すれば取り込める', () {
      final review = state([
        buildGroup([
          ...complete,
          file(
            path: 'subject-a/stray.pdf',
            proposedRole: MaterialRole.reference,
            proposalConfirmed: true,
          ),
        ]),
      ]);

      expect(review.unconfirmedProposals, isEmpty);
      expect(review.canImport, isTrue);
    });

    test('提案が当たっていても、確認しないうちは取り込めない', () {
      // The point of the review step. A proposal being correct is not what
      // makes it safe to import -- accuracy has not been measured at all.
      final review = state([
        buildGroup([
          ...complete,
          file(
            path: 'subject-a/03_resource.pdf',
            proposedRole: MaterialRole.annotationResource,
          ),
        ]),
      ]);

      expect(review.canImport, isFalse);
    });

    test('役割を自分で選べば、それが確認になる', () {
      final review = state([
        buildGroup([
          ...complete,
          file(
            path: 'subject-a/stray.pdf',
            proposedRole: MaterialRole.reference,
            humanRole: MaterialRole.annotationSample,
            proposalConfirmed: true,
          ),
        ]),
      ]);

      expect(review.canImport, isTrue);
    });

    test('除外したファイルは確認を求めない', () {
      // Deciding not to import something is itself a decision.
      final review = state([
        buildGroup([
          ...complete,
          file(
            path: 'subject-a/stray.pdf',
            proposedRole: MaterialRole.reference,
            excluded: true,
          ),
        ]),
      ]);

      expect(review.canImport, isTrue);
    });

    test('規則が当てたファイルは確認を求めない', () {
      // A rule is a stated intention the reviewer can see in the list, not a
      // guess -- and it is what keeps a folder of forty answers from costing
      // forty confirmations.
      final review = state([buildGroup(complete)]);

      expect(review.unconfirmedProposals, isEmpty);
      expect(review.canImport, isTrue);
    });

    test('役割が決まらないファイルが残っていれば取り込めない', () {
      final review = state([
        buildGroup([...complete, file(path: 'subject-a/stray.pdf')]),
      ]);

      expect(review.canImport, isFalse);
    });
  });

  group('取り込み先 (追記A: 2週目以降の流れ)', () {
    test('登録済みのテストに紐づければ採点基準は要らない', () {
      // Criteria arrive once for every subject; answers arrive weekly. Without
      // this, week two is blocked on a file the test already has.
      final review = state([
        buildGroup(
          [file(ruleRole: MaterialRole.studentAnswer)],
          kind: IntakeTargetKind.existing,
          testId: 'test-1',
          missing: const [MaterialRole.gradingCriteria],
        ),
      ]);

      expect(review.groups.single.unmetRequirements, isEmpty);
      expect(review.canImport, isTrue);
    });

    test('新しいテストとして登録するなら採点基準が要る', () {
      final review = state([
        buildGroup(
          [file(ruleRole: MaterialRole.studentAnswer)],
          missing: const [MaterialRole.gradingCriteria],
        ),
      ]);

      expect(review.groups.single.unmetRequirements, [
        MaterialRole.gradingCriteria,
      ]);
      expect(review.canImport, isFalse);
    });

    test('取り込み先を決めていない group は取り込めない', () {
      final review = state([
        buildGroup(complete, kind: IntakeTargetKind.unassigned),
      ]);

      expect(review.canImport, isFalse);
    });

    test('テスト名が空なら取り込めない', () {
      final review = state([buildGroup(complete, name: '   ')]);

      expect(review.canImport, isFalse);
    });
  });

  group('答案ごとの振り分け', () {
    test('振り分け先の決まっていない答案があれば取り込めない', () {
      final review = state([
        buildGroup([
          file(ruleRole: MaterialRole.studentAnswer),
        ], kind: IntakeTargetKind.perAnswer),
      ]);

      expect(review.groups.single.unroutedAnswers, hasLength(1));
      expect(review.canImport, isFalse);
    });

    test('すべての答案に振り分け先があれば取り込める', () {
      final review = state([
        buildGroup([
          file(ruleRole: MaterialRole.studentAnswer, answerTestId: 'test-1'),
        ], kind: IntakeTargetKind.perAnswer),
      ]);

      expect(review.canImport, isTrue);
    });

    test('答案以外のファイルは振り分け先が決まらないので取り込めない', () {
      // Routing per answer says nothing about where a 採点基準 in the same
      // folder should go. Guessing would attach material to a test nobody
      // chose.
      final review = state([
        buildGroup([
          file(ruleRole: MaterialRole.studentAnswer, answerTestId: 'test-1'),
          file(
            path: 'subject-a/02_criteria.pdf',
            ruleRole: MaterialRole.gradingCriteria,
          ),
        ], kind: IntakeTargetKind.perAnswer),
      ]);

      expect(review.groups.single.unroutableNonAnswers, hasLength(1));
      expect(review.canImport, isFalse);
    });
  });

  group('費用の見積もり (受入条件7)', () {
    test('規則が当たったファイルは見積もりに数えない (受入条件8)', () {
      final review = state([buildGroup(complete)]);

      expect(review.pendingClassification, isEmpty);
    });

    test('自分で役割を決めたファイルは、もう問い合わせない', () {
      // Paying to classify a file whose role is already chosen is money spent
      // on a question with no consequence.
      final review = state([
        buildGroup([
          ...complete,
          file(
            path: 'subject-a/stray.pdf',
            needsClassification: true,
            humanRole: MaterialRole.reference,
            proposalConfirmed: true,
          ),
        ]),
      ]);

      expect(review.pendingClassification, isEmpty);
    });

    test('除外したファイルも、もう問い合わせない', () {
      final review = state([
        buildGroup([
          ...complete,
          file(
            path: 'subject-a/stray.pdf',
            needsClassification: true,
            excluded: true,
          ),
        ]),
      ]);

      expect(review.pendingClassification, isEmpty);
    });

    test('単価が未設定なら費用は出さない (0円と言わない)', () {
      // This app cannot know what a provider charges. Printing 0 would read as
      // "free", which is a claim nobody verified.
      final review = state([
        buildGroup([
          ...complete,
          file(path: 'subject-a/stray.pdf', needsClassification: true),
        ]),
      ]);

      expect(review.pendingClassification, hasLength(1));
      expect(review.estimatedCostForCalls(1), isNull);
    });

    test('単価があれば件数×単価で出す', () {
      final review = state([
        buildGroup([
          ...complete,
          file(path: 'subject-a/stray-1.pdf', needsClassification: true),
          file(path: 'subject-a/stray-2.pdf', needsClassification: true),
        ]),
      ], unitCost: 1.5);

      expect(review.estimatedCostForCalls(2), 3.0);
    });
  });

  group('計画からの組み立て', () {
    test('取り込まないと判定されたファイルは、はじめから除外されている', () {
      final plan = IntakePlanResponse(
        (builder) => builder
          ..groups.replace([
            PlannedGroupModel(
              (g) => g
                ..key = 'subject-a'
                ..suggestedName = 'subject-a'
                ..missingRequiredRolesIfNew.replace(const <MaterialRole>[])
                ..files.replace([
                  PlannedFileModel(
                    (f) => f
                      ..relativePath = 'subject-a/how-to-use.txt'
                      ..sha256 = '0' * 64
                      ..sizeBytes = 10
                      ..role = MaterialRole.ignore
                      ..roleSource = RoleSource.rule
                      ..classification = ClassificationNeed.notNeeded,
                  ),
                ]),
            ),
          ])
          ..estimate.replace(
            ClassificationEstimateModel(
              (e) => e
                ..pending = 0
                ..cached = 0
                ..unsupported = 0
                ..notNeeded = 1,
            ),
          ),
      );

      final review = buildReviewState(
        plan: plan,
        folder: const ScannedFolder(name: 'subject-a', entries: []),
        requiredRoles: const [],
      );

      expect(review.groups.single.files.single.excluded, isTrue);
      expect(review.groups.single.includedFiles, isEmpty);
    });
  });

  group('コードレビュー1回目で見つかった穴', () {
    test('提案をまとめて確認できる（40件を40回押させない）', () {
      final review = state([
        buildGroup([
          ...complete,
          for (var i = 0; i < 40; i++)
            file(
              path: 'subject-a/stray-$i.pdf',
              proposedRole: MaterialRole.studentAnswer,
            ),
        ]),
      ]);
      expect(review.confirmableProposals, hasLength(40));
      expect(review.canImport, isFalse);

      final confirmed = review.confirmAllProposals();

      expect(confirmed.unconfirmedProposals, isEmpty);
      expect(confirmed.canImport, isTrue);
    });

    test('提案が無いファイルは、まとめて確認しても確認済みにならない', () {
      // "Nobody knows what this is" must not become "the reviewer said it was
      // fine". That is the one thing the confirmation step exists to prevent.
      final review = state([
        buildGroup([...complete, file(path: 'subject-a/stray.pdf')]),
      ]).confirmAllProposals();

      expect(review.canImport, isFalse);
      expect(review.unconfirmedProposals, hasLength(1));
    });

    test('キャッシュ済みのファイルも問い合わせ対象に含める', () {
      // The sidecar already holds the answer; it is free but still has to be
      // asked for. Treating cached as "nothing to do" left a re-selected
      // folder with forty rows to decide by hand.
      final review = state([
        buildGroup([
          ...complete,
          file(path: 'subject-a/cached.pdf', cached: true),
          file(path: 'subject-a/new.pdf', needsClassification: true),
        ]),
      ]);

      expect(review.classifiableFiles, hasLength(2));
      // ...but only the new one costs anything.
      expect(review.pendingClassification, hasLength(1));
    });

    test('答案の振り分けも費用の見積もりに数える', () {
      // Forty answers whose roles every rule matched cost nothing to classify
      // and forty calls to attribute. Counting only the first would tell the
      // reviewer the run is free right before charging them for it.
      final review = state([
        buildGroup([
          for (var i = 0; i < 40; i++)
            file(
              path: 'subject-a/01_answers-$i.pdf',
              ruleRole: MaterialRole.studentAnswer,
            ),
        ], kind: IntakeTargetKind.perAnswer),
      ], unitCost: 2.0);

      expect(review.pendingClassification, isEmpty);
      expect(review.answersNeedingAttribution, hasLength(40));
      expect(review.estimatedCostForCalls(40), 80.0);
    });

    test('振り分け済みの答案は、もう振り分けの費用に数えない', () {
      final review = state([
        buildGroup([
          file(ruleRole: MaterialRole.studentAnswer, answerTestId: 'test-1'),
        ], kind: IntakeTargetKind.perAnswer),
      ]);

      expect(review.answersNeedingAttribution, isEmpty);
    });

    test('1つのテストに紐づける group は振り分けを必要としない', () {
      final review = state([
        buildGroup(
          [file(ruleRole: MaterialRole.studentAnswer)],
          kind: IntakeTargetKind.existing,
          testId: 'test-1',
          missing: const [MaterialRole.gradingCriteria],
        ),
      ]);

      expect(review.answersNeedingAttribution, isEmpty);
    });

    test('振り分け先を解除できる（候補から外れたとき）', () {
      final review =
          state([
            buildGroup([
              file(
                ruleRole: MaterialRole.studentAnswer,
                answerTestId: 'test-1',
              ),
            ], kind: IntakeTargetKind.perAnswer),
          ]).withFile(
            'subject-a/01_answers.pdf',
            (current) => current.copyWith(clearAnswerTestId: true),
          );

      expect(review.groups.single.files.single.answerTestId, isNull);
      expect(review.canImport, isFalse);
    });
  });

  group('コードレビュー2回目で見つかった穴', () {
    test('AIが振り分けた答案も、確認するまでは取り込めない [P1]', () {
      // Attribution decides which criteria an answer is graded against, so a
      // wrong one is graded silently against another test's rubric. The role
      // discipline has to hold here too -- more so, not less.
      final review = state([
        buildGroup([
          file(
            ruleRole: MaterialRole.studentAnswer,
            proposedAnswerTestId: 'test-1',
          ),
        ], kind: IntakeTargetKind.perAnswer),
      ]);

      expect(review.groups.single.unconfirmedAttributions, hasLength(1));
      expect(review.unconfirmedProposals, hasLength(1));
      expect(review.canImport, isFalse);
    });

    test('振り分けの提案を確認すれば取り込める', () {
      final review = state([
        buildGroup([
          file(
            ruleRole: MaterialRole.studentAnswer,
            proposedAnswerTestId: 'test-1',
          ),
        ], kind: IntakeTargetKind.perAnswer),
      ]).confirmAllProposals();

      expect(review.groups.single.files.single.answerTestId, 'test-1');
      expect(review.canImport, isTrue);
    });

    test('振り分けの提案も一括確認の件数に入る', () {
      final review = state([
        buildGroup([
          for (var i = 0; i < 40; i++)
            file(
              path: 'subject-a/01_answers-$i.pdf',
              ruleRole: MaterialRole.studentAnswer,
              proposedAnswerTestId: 'test-1',
            ),
        ], kind: IntakeTargetKind.perAnswer),
      ]);

      expect(review.confirmableProposals, hasLength(40));
    });

    test('提案の無い答案は、一括確認でも振り分けられない', () {
      // "Could not tell" must not become "the reviewer said test-1".
      final review = state([
        buildGroup([
          file(ruleRole: MaterialRole.studentAnswer),
        ], kind: IntakeTargetKind.perAnswer),
      ]).confirmAllProposals();

      expect(review.groups.single.files.single.answerTestId, isNull);
      expect(review.canImport, isFalse);
    });

    test('一度問い合わせた答案は、振り分けの見積もりに二度数えない', () {
      final review = state([
        buildGroup([
          file(
            ruleRole: MaterialRole.studentAnswer,
            attributionAttempted: true,
          ),
        ], kind: IntakeTargetKind.perAnswer),
      ]);

      expect(review.groups.single.unroutedAnswers, hasLength(1));
      expect(review.answersNeedingAttribution, isEmpty);
    });
  });

  group('コードレビュー4回目で見つかった穴', () {
    test('確認画面で採点基準を除外したら、不足として検出する [P2-1]', () {
      // The plan said nothing was missing, because at plan time nothing was.
      // The confirmation screen is an editing screen, so the check has to run
      // against what is included *now*.
      final withCriteria = buildGroup(
        [
          file(ruleRole: MaterialRole.studentAnswer),
          file(
            path: 'subject-a/02_criteria.pdf',
            ruleRole: MaterialRole.gradingCriteria,
          ),
        ],
        missing: const [
          MaterialRole.studentAnswer,
          MaterialRole.gradingCriteria,
        ],
      );
      expect(state([withCriteria]).canImport, isTrue);

      final withoutCriteria = state([withCriteria]).withFile(
        'subject-a/02_criteria.pdf',
        (current) => current.copyWith(excluded: true),
      );

      expect(withoutCriteria.groups.single.unmetRequirements, [
        MaterialRole.gradingCriteria,
      ]);
      expect(withoutCriteria.canImport, isFalse);
    });

    test('除外を戻せば、また取り込める', () {
      final review = state([
        buildGroup(
          [
            file(ruleRole: MaterialRole.studentAnswer),
            file(
              path: 'subject-a/02_criteria.pdf',
              ruleRole: MaterialRole.gradingCriteria,
            ),
          ],
          missing: const [
            MaterialRole.studentAnswer,
            MaterialRole.gradingCriteria,
          ],
        ),
      ]);
      final excluded = review.withFile(
        'subject-a/02_criteria.pdf',
        (current) => current.copyWith(excluded: true),
      );
      final restored = excluded.withFile(
        'subject-a/02_criteria.pdf',
        (current) => current.copyWith(excluded: false),
      );

      expect(restored.groups.single.unmetRequirements, isEmpty);
      expect(restored.canImport, isTrue);
    });

    test('役割を変えて必須役割が欠けた場合も検出する', () {
      // Not only exclusion: re-labelling the criteria as something else
      // removes it just as effectively.
      final review =
          state([
            buildGroup(
              [
                file(ruleRole: MaterialRole.studentAnswer),
                file(
                  path: 'subject-a/02_criteria.pdf',
                  ruleRole: MaterialRole.gradingCriteria,
                ),
              ],
              missing: const [
                MaterialRole.studentAnswer,
                MaterialRole.gradingCriteria,
              ],
            ),
          ]).withFile(
            'subject-a/02_criteria.pdf',
            (current) => current.copyWith(
              humanRole: MaterialRole.reference,
              proposalConfirmed: true,
            ),
          );

      expect(review.groups.single.unmetRequirements, [
        MaterialRole.gradingCriteria,
      ]);
      expect(review.canImport, isFalse);
    });
  });

  group('requiredRolesOf (Issue #126)', () {
    IntakeRuleModel rule(MaterialRole role, {Requirement? requirement}) =>
        IntakeRuleModel(
          (b) => b
            ..pattern = '*'
            ..scope = RuleScope.file
            ..requirement = requirement
            ..role = role,
        );

    IntakeTemplateModel template(String id, List<IntakeRuleModel> rules) =>
        IntakeTemplateModel(
          (b) => b
            ..id = id
            ..name = id
            ..rules.replace(rules),
        );

    test('必須の役割だけを、規則の順で返す', () {
      final roles = requiredRolesOf(
        templates: [
          template('t1', [
            rule(
              MaterialRole.gradingCriteria,
              requirement: Requirement.required_,
            ),
            rule(
              MaterialRole.studentAnswer,
              requirement: Requirement.recommended,
            ),
            rule(MaterialRole.reference, requirement: Requirement.required_),
          ]),
        ],
        templateId: 't1',
      );

      expect(roles, [MaterialRole.gradingCriteria, MaterialRole.reference]);
    });

    test('同じ役割が複数回必須でも一度だけ', () {
      final roles = requiredRolesOf(
        templates: [
          template('t1', [
            rule(
              MaterialRole.gradingCriteria,
              requirement: Requirement.required_,
            ),
            rule(
              MaterialRole.gradingCriteria,
              requirement: Requirement.required_,
            ),
          ]),
        ],
        templateId: 't1',
      );

      expect(roles, [MaterialRole.gradingCriteria]);
    });

    test('存在しないテンプレートIDなら空', () {
      expect(
        requiredRolesOf(templates: const [], templateId: 'missing'),
        isEmpty,
      );
    });
  });

  group('pruneStaleTargets (Issue #126)', () {
    test('消えたテストへの existing 指定は unassigned に戻す', () {
      final review = state([
        buildGroup([file()], kind: IntakeTargetKind.existing, testId: 'gone'),
      ]);

      final pruned = pruneStaleTargets(review, {'still-here'});

      expect(pruned.groups.single.targetKind, IntakeTargetKind.unassigned);
      expect(pruned.groups.single.targetTestId, isNull);
    });

    test('登録済みテストが残っていれば existing 指定は変えない', () {
      final review = state([
        buildGroup([file()], kind: IntakeTargetKind.existing, testId: 't1'),
      ]);

      final pruned = pruneStaleTargets(review, {'t1'});

      expect(pruned.groups.single.targetKind, IntakeTargetKind.existing);
      expect(pruned.groups.single.targetTestId, 't1');
    });

    test('登録済みテストが1件も無くなったら perAnswer は unassigned に戻す', () {
      // The dropdown offering "答案ごとに登録済みのテストへ振り分ける" disappears
      // with the last registered test, so a group still in that mode would
      // hold a value with no matching item.
      final review = state([
        buildGroup([file()], kind: IntakeTargetKind.perAnswer),
      ]);

      final pruned = pruneStaleTargets(review, const {});

      expect(pruned.groups.single.targetKind, IntakeTargetKind.unassigned);
    });

    test('登録済みテストが残っていれば perAnswer のままにする', () {
      final review = state([
        buildGroup([file()], kind: IntakeTargetKind.perAnswer),
      ]);

      final pruned = pruneStaleTargets(review, {'t1'});

      expect(pruned.groups.single.targetKind, IntakeTargetKind.perAnswer);
    });
  });
}
