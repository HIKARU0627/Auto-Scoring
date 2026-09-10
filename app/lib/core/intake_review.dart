/// The confirmation step of intake, as state rather than widgets
/// (Issue #101 stage 3).
///
/// This is where the rule that matters lives: **nothing is imported that a
/// human has not confirmed.** The classifier's accuracy has not been measured
/// -- the material on hand holds one answer per subject, so there is no second
/// answer for the same test to measure against -- and until it has been, a
/// setting that skips the review would let a silently misfiled answer be
/// graded against the wrong test's criteria.
///
/// Kept out of the widget so the rule can be tested directly, without driving
/// a screen to find out whether a button was enabled.
library;

import 'package:auto_scoring_app/api/sidecar_api_client.dart';
import 'package:auto_scoring_app/core/folder_scan.dart';

/// What a group of files will be imported into.
enum IntakeTargetKind {
  /// Create a new test. Needs the template's required roles present.
  create,

  /// Add to a test that is already registered. Needs no grading criteria --
  /// that test already has one. This is the weekly flow: criteria arrive once
  /// for eleven subjects, answers arrive every week.
  existing,

  /// The answers in this group belong to *different* already-registered
  /// tests, and each one is routed individually.
  ///
  /// Restricted to already-registered tests on purpose. That is the shape the
  /// reported workflow actually has -- criteria arrive once for every subject,
  /// answers arrive weekly for tests that already exist -- and it keeps
  /// routing independent of the order tests are created in. A batch that also
  /// *creates* several tests and needs its answers split between them is
  /// handled by putting them in folders, which the template already splits.
  perAnswer,

  /// The reviewer has not said yet.
  unassigned,
}

/// Where a file's role came from, once the reviewer's own edits are folded in.
enum IntakeRoleOrigin { rule, proposal, human, unresolved }

/// One file on the confirmation screen.
class IntakeFileState {
  const IntakeFileState({
    required this.relativePath,
    required this.absolutePath,
    required this.sha256,
    required this.sizeBytes,
    required this.ruleRole,
    required this.needsClassification,
    this.cachedClassification = false,
    this.classificationAttempted = false,
    this.proposedRole,
    this.proposalConfirmed = false,
    this.humanRole,
    this.excluded = false,
    this.answerTestId,
    this.proposedAnswerTestId,
    this.attributionAttempted = false,
  });

  final String relativePath;
  final String absolutePath;
  final String sha256;
  final int sizeBytes;

  /// What a template rule proposed, or `null` if none matched.
  final MaterialRole? ruleRole;

  /// Whether an LLM call would be spent on this file.
  final bool needsClassification;

  /// Whether the sidecar already holds an answer for this content.
  ///
  /// Distinct from [needsClassification] because the two differ in *cost*,
  /// not in whether the answer is wanted: a cached file still has to be asked
  /// for, it is simply free. Treating "cached" as "nothing to do" is what made
  /// re-selecting a folder drop every proposal it had already paid for and
  /// leave forty rows to decide by hand.
  final bool cachedClassification;

  /// Whether the classifier has already been asked about this file.
  ///
  /// Set even when the answer was "could not tell" -- which is a real answer,
  /// and asking again would spend the same money for the same reply. Without
  /// it, pressing 「AIで判定する」 a second time re-charges for every file the
  /// classifier declined to decide the first time.
  final bool classificationAttempted;

  /// What the classifier proposed. `null` either because nothing was asked or
  /// because it answered "could not tell" -- [proposalConfirmed] distinguishes
  /// the two.
  final MaterialRole? proposedRole;

  /// Whether the reviewer has looked at [proposedRole] and accepted it.
  ///
  /// A proposal that is right is still unconfirmed until this is true. That is
  /// the point: correctness of the guess is not what makes it safe to import.
  final bool proposalConfirmed;

  /// What the reviewer chose, overriding everything above.
  final MaterialRole? humanRole;

  final bool excluded;

  /// Which already-registered test this answer goes to, when its group routes
  /// answers individually.
  ///
  /// **A confirmed value, always.** A classifier's answer lands in
  /// [proposedAnswerTestId] and only moves here when the reviewer accepts it,
  /// exactly like [humanRole] versus [proposedRole].
  ///
  /// The split matters more here than it does for roles: attribution decides
  /// **which criteria an answer is graded against**, so a wrong one is graded
  /// silently against another test's rubric. A wrong role is visible in a
  /// list; a wrong attribution is not.
  final String? answerTestId;

  /// What the classifier proposed as this answer's test. `null` when nothing
  /// was asked, or when it answered "could not tell".
  final String? proposedAnswerTestId;

  /// Whether the classifier has already been asked which test this answer
  /// belongs to.
  ///
  /// Same reason as [classificationAttempted]: "could not tell" is a real
  /// answer, and asking again buys the same reply at the same price.
  final bool attributionAttempted;

  String get fileName => relativePath.split('/').last;

  /// The role this file would actually be imported as.
  MaterialRole? get effectiveRole => humanRole ?? ruleRole ?? proposedRole;

  IntakeRoleOrigin get origin {
    if (humanRole != null) return IntakeRoleOrigin.human;
    if (ruleRole != null) return IntakeRoleOrigin.rule;
    if (proposedRole != null || proposalConfirmed) {
      return IntakeRoleOrigin.proposal;
    }
    return IntakeRoleOrigin.unresolved;
  }

  /// Whether this file still needs the reviewer's attention before the batch
  /// can be imported.
  ///
  /// An excluded file never does -- deciding not to import something is itself
  /// a decision. A rule-matched file does not either: the reviewer sees it in
  /// the list, and a rule is a stated intention rather than a guess. What
  /// blocks is an unconfirmed *proposal*, and a file with no role at all.
  bool get blocksImport {
    if (excluded) return false;
    if (humanRole != null) return false;
    if (ruleRole != null) return false;
    return !proposalConfirmed || effectiveRole == null;
  }

  IntakeFileState copyWith({
    MaterialRole? proposedRole,
    bool? classificationAttempted,
    bool? proposalConfirmed,
    MaterialRole? humanRole,
    bool? excluded,
    String? answerTestId,
    String? proposedAnswerTestId,
    bool? attributionAttempted,
    bool clearHumanRole = false,
    bool clearProposedRole = false,
    bool clearAnswerTestId = false,
    bool clearProposedAnswerTestId = false,
  }) => IntakeFileState(
    relativePath: relativePath,
    absolutePath: absolutePath,
    sha256: sha256,
    sizeBytes: sizeBytes,
    ruleRole: ruleRole,
    needsClassification: needsClassification,
    cachedClassification: cachedClassification,
    classificationAttempted:
        classificationAttempted ?? this.classificationAttempted,
    proposedRole: clearProposedRole
        ? null
        : (proposedRole ?? this.proposedRole),
    proposalConfirmed: proposalConfirmed ?? this.proposalConfirmed,
    humanRole: clearHumanRole ? null : (humanRole ?? this.humanRole),
    excluded: excluded ?? this.excluded,
    answerTestId: clearAnswerTestId
        ? null
        : (answerTestId ?? this.answerTestId),
    proposedAnswerTestId: clearProposedAnswerTestId
        ? null
        : (proposedAnswerTestId ?? this.proposedAnswerTestId),
    attributionAttempted: attributionAttempted ?? this.attributionAttempted,
  );
}

/// One folder's worth of files and where they are going.
class IntakeGroupState {
  const IntakeGroupState({
    required this.key,
    required this.name,
    required this.files,
    required this.requiredRoles,
    this.targetKind = IntakeTargetKind.create,
    this.targetTestId,
  });

  final String key;

  /// The test name this group would create. Starts as the folder's own name.
  final String name;

  final List<IntakeFileState> files;

  /// Every role the template marks required -- **the whole set, not what was
  /// missing when the plan was built.**
  ///
  /// The plan's own "missing" list is a snapshot of the moment it was
  /// computed, and this is an editing screen. A group that had its criteria at
  /// plan time and has it excluded now is missing it, and a snapshot cannot
  /// say so: the role was never in that list to begin with (review round 4,
  /// P2-1). Holding the requirement rather than the shortfall makes the check
  /// answerable at any point.
  final List<MaterialRole> requiredRoles;

  final IntakeTargetKind targetKind;
  final String? targetTestId;

  List<IntakeFileState> get includedFiles =>
      files.where((file) => !file.excluded).toList();

  /// Which required roles block this group **right now**.
  ///
  /// Recomputed from [requiredRoles] against the files currently included, so
  /// excluding a file on the confirmation screen is noticed. Computing it from
  /// the plan's shortfall instead meant an exclusion made after planning was
  /// invisible, and the batch went to the completion screen and failed there
  /// rather than staying on the screen that could fix it.
  ///
  /// Empty for a group bound to an existing test: the criteria a new test
  /// would need are already attached to the test being added to. Advisory
  /// either way -- what really prevents a criteria-less test is `POST /tests`,
  /// which cannot be called without that file.
  List<MaterialRole> get unmetRequirements {
    if (targetKind != IntakeTargetKind.create) return const [];
    final present = includedFiles.map((file) => file.effectiveRole).toSet();
    return requiredRoles.where((role) => !present.contains(role)).toList();
  }

  /// Answers still waiting to be routed, when this group routes individually.
  List<IntakeFileState> get unroutedAnswers {
    if (targetKind != IntakeTargetKind.perAnswer) return const [];
    return includedFiles
        .where(
          (file) =>
              file.effectiveRole == MaterialRole.studentAnswer &&
              file.answerTestId == null,
        )
        .toList();
  }

  /// Answers carrying an attribution proposal the reviewer has not accepted.
  ///
  /// These block the import exactly like an unconfirmed role proposal does.
  /// They are a subset of [unroutedAnswers] -- an answer with a proposal is
  /// still unrouted until somebody confirms it.
  List<IntakeFileState> get unconfirmedAttributions {
    if (targetKind != IntakeTargetKind.perAnswer) return const [];
    return unroutedAnswers
        .where((file) => file.proposedAnswerTestId != null)
        .toList();
  }

  /// Included files that are not answers, when this group routes individually.
  ///
  /// Routing per answer says nothing about where a 採点基準 in the same folder
  /// should go, so those files block until the reviewer excludes them or
  /// picks a different target for the group. Guessing would attach material
  /// to a test nobody chose.
  List<IntakeFileState> get unroutableNonAnswers {
    if (targetKind != IntakeTargetKind.perAnswer) return const [];
    return includedFiles
        .where((file) => file.effectiveRole != MaterialRole.studentAnswer)
        .toList();
  }

  bool get isReady {
    if (targetKind == IntakeTargetKind.unassigned) return false;
    if (includedFiles.isEmpty) return false;
    if (unmetRequirements.isNotEmpty) return false;
    if (targetKind == IntakeTargetKind.create && name.trim().isEmpty) {
      return false;
    }
    if (unroutedAnswers.isNotEmpty || unroutableNonAnswers.isNotEmpty) {
      return false;
    }
    return !includedFiles.any((file) => file.blocksImport);
  }

  IntakeGroupState copyWith({
    String? name,
    List<IntakeFileState>? files,
    IntakeTargetKind? targetKind,
    String? targetTestId,
    bool clearTargetTestId = false,
  }) => IntakeGroupState(
    key: key,
    name: name ?? this.name,
    files: files ?? this.files,
    requiredRoles: requiredRoles,
    targetKind: targetKind ?? this.targetKind,
    targetTestId: clearTargetTestId
        ? null
        : (targetTestId ?? this.targetTestId),
  );
}

/// The whole confirmation screen's state.
class IntakeReviewState {
  const IntakeReviewState({required this.groups, this.unitCost});

  final List<IntakeGroupState> groups;

  /// The per-call price the reviewer entered, or `null` for "not set".
  ///
  /// `null` is not zero: this app cannot know what a provider charges, and
  /// showing an invented figure would be worse than saying so.
  final double? unitCost;

  List<IntakeFileState> get allFiles => [
    for (final group in groups) ...group.files,
  ];

  /// Every file still worth asking the classifier about, cached or not.
  ///
  /// This is what the run actually iterates. [pendingClassification] is the
  /// subset that costs money, and is what the estimate shows.
  List<IntakeFileState> get classifiableFiles => allFiles
      .where(
        (file) =>
            (file.needsClassification || file.cachedClassification) &&
            !file.classificationAttempted &&
            !file.excluded &&
            file.humanRole == null &&
            file.proposedRole == null &&
            !file.proposalConfirmed,
      )
      .toList();

  /// Files a classification call would still be spent on.
  ///
  /// Excludes anything the reviewer already excluded or decided themselves --
  /// paying to classify a file nobody will import, or one whose role is
  /// already chosen, is money spent on a question with no consequence.
  List<IntakeFileState> get pendingClassification => allFiles
      .where(
        (file) =>
            file.needsClassification &&
            !file.classificationAttempted &&
            !file.excluded &&
            file.humanRole == null &&
            file.proposedRole == null &&
            !file.proposalConfirmed,
      )
      .toList();

  /// Proposals the reviewer has not looked at yet -- of either kind.
  ///
  /// While this is non-empty the batch cannot be imported. Not a warning: the
  /// import action is unavailable.
  List<IntakeFileState> get unconfirmedProposals => [
    ...allFiles.where((file) => file.blocksImport),
    for (final group in groups) ...group.unconfirmedAttributions,
  ];

  /// Whether the batch can be imported at all.
  bool get canImport =>
      groups.isNotEmpty &&
      groups.any((group) => group.includedFiles.isNotEmpty) &&
      groups.every((group) => group.includedFiles.isEmpty || group.isReady);

  /// Answers that would each cost an **attribution** call.
  ///
  /// Counted separately from [pendingClassification] because they are a
  /// different question asked of the same provider, and because they are easy
  /// to miss: a folder of forty answers whose roles every rule matched shows
  /// zero role-classification calls while still being about to spend forty
  /// attribution calls. Showing only the first number would tell the reviewer
  /// their run is free right before charging them for it.
  ///
  /// Only groups routing answers individually contribute -- a group bound to
  /// one test has nothing to attribute.
  /// Excludes answers already asked about: the classifier will not be asked
  /// again, so counting them would overstate what the run costs.
  List<IntakeFileState> get answersNeedingAttribution => [
    for (final group in groups)
      if (group.targetKind == IntakeTargetKind.perAnswer)
        ...group.unroutedAnswers.where(
          (answer) => !answer.attributionAttempted,
        ),
  ];

  /// Estimated cost of ``calls`` provider requests, or `null` when no unit
  /// price has been entered -- in which case the screen says the price is
  /// unknown rather than printing a zero that looks like "free".
  double? estimatedCostForCalls(int calls) =>
      unitCost == null ? null : unitCost! * calls;

  /// ``clearUnitCost`` exists because ``null`` cannot mean both "leave it
  /// alone" and "there is no price".
  ///
  /// This screen has spent the whole Issue distinguishing "unset" from "zero"
  /// -- a `copyWith` that folds an explicit null back into the previous value
  /// quietly undoes that. Clearing the price in settings and returning left
  /// the estimate holding the old figure while the screen thought there was
  /// none, which then threw (review round 3, P1-3).
  IntakeReviewState copyWith({
    List<IntakeGroupState>? groups,
    double? unitCost,
    bool clearUnitCost = false,
  }) => IntakeReviewState(
    groups: groups ?? this.groups,
    unitCost: clearUnitCost ? null : (unitCost ?? this.unitCost),
  );

  IntakeReviewState withFile(
    String relativePath,
    IntakeFileState Function(IntakeFileState) update,
  ) => copyWith(
    groups: [
      for (final group in groups)
        group.copyWith(
          files: [
            for (final file in group.files)
              file.relativePath == relativePath ? update(file) : file,
          ],
        ),
    ],
  );

  /// Mark every proposal the reviewer is looking at as confirmed.
  ///
  /// The explicit bulk approval a folder of forty answers needs: without it,
  /// a batch whose names match no rule costs one tap per file, which is the
  /// exact cost this Issue exists to remove.
  ///
  /// **Only files that actually carry a proposal.** A file the classifier
  /// could not decide, or was never asked about, has nothing to approve --
  /// confirming it would turn "nobody knows what this is" into "the reviewer
  /// said it was fine", which is the one thing the confirmation step exists to
  /// prevent. Those stay blocking until a role is chosen.
  ///
  /// Covers **both** kinds of proposal: the role a file was given, and the
  /// test an answer was attributed to. Leaving attribution out would mean the
  /// discipline held for the cheaper mistake and not the more expensive one.
  IntakeReviewState confirmAllProposals() => copyWith(
    groups: [
      for (final group in groups)
        group.copyWith(
          files: [
            for (final file in group.files)
              file.excluded
                  ? file
                  : file.copyWith(
                      proposalConfirmed: file.proposedRole != null
                          ? true
                          : null,
                      answerTestId:
                          group.targetKind == IntakeTargetKind.perAnswer &&
                              file.answerTestId == null
                          ? file.proposedAnswerTestId
                          : null,
                    ),
          ],
        ),
    ],
  );

  /// Files carrying a proposal the reviewer has not accepted yet, of either
  /// kind.
  List<IntakeFileState> get confirmableProposals => [
    ...allFiles.where(
      (file) =>
          !file.excluded &&
          file.proposedRole != null &&
          !file.proposalConfirmed &&
          file.humanRole == null,
    ),
    for (final group in groups) ...group.unconfirmedAttributions,
  ];

  IntakeReviewState withGroup(
    String key,
    IntakeGroupState Function(IntakeGroupState) update,
  ) => copyWith(
    groups: [
      for (final group in groups) group.key == key ? update(group) : group,
    ],
  );
}

/// The roles [templateId] marks required, in rule order and de-duplicated.
///
/// Extracted from `features/intake/intake_page.dart` (Issue #126). Read from
/// the template the reviewer selected rather than from a plan already built:
/// a plan reports what was *missing* when it was computed, and a reviewer can
/// exclude a file from the confirmation screen afterwards, at which point the
/// plan's snapshot no longer says what the template actually requires.
List<MaterialRole> requiredRolesOf({
  required List<IntakeTemplateModel> templates,
  required String templateId,
}) {
  final template = templates.where((entry) => entry.id == templateId);
  if (template.isEmpty) return const [];
  final roles = <MaterialRole>[];
  for (final rule in template.first.rules) {
    if (rule.requirement == Requirement.required_ &&
        !roles.contains(rule.role)) {
      roles.add(rule.role);
    }
  }
  return roles;
}

/// Resets any group's target that no longer names a test in
/// [knownTestIds] -- the registered-test list this screen re-reads at the
/// start of every batch.
///
/// Extracted from `_IntakePageState._applyExistingTests` (Issue #126). Left
/// alone, a stale target produces two failures, both found by sweeping for
/// values held across a state change:
///
/// * a group bound to a test that has since gone still reports itself ready
///   and fails at import time with a dead id -- on the completion screen,
///   which cannot fix it;
/// * a group routing answers individually keeps that mode after the last
///   registered test disappears, so its dropdown holds a value with no
///   matching item and asserts.
///
/// Reset to "not chosen" rather than left as-is: losing a choice is worth
/// saying out loud, silently keeping an impossible one is not.
IntakeReviewState pruneStaleTargets(
  IntakeReviewState review,
  Set<String> knownTestIds,
) => review.copyWith(
  groups: [
    for (final group in review.groups)
      if (group.targetKind == IntakeTargetKind.existing &&
          !knownTestIds.contains(group.targetTestId))
        group.copyWith(
          targetKind: IntakeTargetKind.unassigned,
          clearTargetTestId: true,
        )
      else if (group.targetKind == IntakeTargetKind.perAnswer &&
          knownTestIds.isEmpty)
        group.copyWith(targetKind: IntakeTargetKind.unassigned)
      else
        group,
  ],
);

/// Build the initial review state from a sidecar plan and the scan it came
/// from.
///
/// The scan is needed because the plan deliberately carries no absolute paths
/// -- it was built from a listing, and the files themselves never left the
/// machine.
///
/// ``requiredRoles`` comes from the template the reviewer selected, not from
/// the plan: the plan reports what was *missing* when it was computed, which
/// stops being true the moment they exclude something here.
IntakeReviewState buildReviewState({
  required IntakePlanResponse plan,
  required ScannedFolder folder,
  required List<MaterialRole> requiredRoles,
  double? unitCost,
}) {
  final byPath = {
    for (final entry in folder.entries) entry.relativePath: entry,
  };
  return IntakeReviewState(
    unitCost: unitCost,
    groups: [
      for (final group in plan.groups)
        IntakeGroupState(
          key: group.key,
          name: group.suggestedName,
          requiredRoles: requiredRoles,
          files: [
            for (final file in group.files)
              IntakeFileState(
                relativePath: file.relativePath,
                absolutePath: byPath[file.relativePath]?.absolutePath ?? '',
                sha256: file.sha256,
                sizeBytes: file.sizeBytes,
                ruleRole: file.role,
                needsClassification:
                    file.classification == ClassificationNeed.pending,
                cachedClassification:
                    file.classification == ClassificationNeed.cached,
                // A file the rules resolved to "do not import" starts
                // excluded rather than listed as something to decide -- the
                // template already said so, and the reviewer can still
                // include it.
                excluded: file.role == MaterialRole.ignore,
              ),
          ],
        ),
    ],
  );
}
