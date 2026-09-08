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
    this.proposedRole,
    this.proposalConfirmed = false,
    this.humanRole,
    this.excluded = false,
    this.answerTestId,
  });

  final String relativePath;
  final String absolutePath;
  final String sha256;
  final int sizeBytes;

  /// What a template rule proposed, or `null` if none matched.
  final MaterialRole? ruleRole;

  /// Whether an LLM call would be spent on this file.
  final bool needsClassification;

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
  /// answers individually. `null` until decided -- by the reviewer, or by a
  /// proposal the reviewer accepted.
  final String? answerTestId;

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
    bool? proposalConfirmed,
    MaterialRole? humanRole,
    bool? excluded,
    String? answerTestId,
    bool clearHumanRole = false,
    bool clearProposedRole = false,
  }) => IntakeFileState(
    relativePath: relativePath,
    absolutePath: absolutePath,
    sha256: sha256,
    sizeBytes: sizeBytes,
    ruleRole: ruleRole,
    needsClassification: needsClassification,
    proposedRole: clearProposedRole
        ? null
        : (proposedRole ?? this.proposedRole),
    proposalConfirmed: proposalConfirmed ?? this.proposalConfirmed,
    humanRole: clearHumanRole ? null : (humanRole ?? this.humanRole),
    excluded: excluded ?? this.excluded,
    answerTestId: answerTestId ?? this.answerTestId,
  );
}

/// One folder's worth of files and where they are going.
class IntakeGroupState {
  const IntakeGroupState({
    required this.key,
    required this.name,
    required this.files,
    required this.missingRequiredRolesIfNew,
    this.targetKind = IntakeTargetKind.create,
    this.targetTestId,
  });

  final String key;

  /// The test name this group would create. Starts as the folder's own name.
  final String name;

  final List<IntakeFileState> files;

  /// What the template's required roles would find missing, computed by the
  /// sidecar under the assumption this becomes a new test.
  final List<MaterialRole> missingRequiredRolesIfNew;

  final IntakeTargetKind targetKind;
  final String? targetTestId;

  List<IntakeFileState> get includedFiles =>
      files.where((file) => !file.excluded).toList();

  /// Which required roles actually block this group.
  ///
  /// Empty for a group bound to an existing test: the criteria a new test
  /// would need are already attached to the test being added to. Advisory
  /// either way -- what really prevents a criteria-less test is `POST /tests`,
  /// which cannot be called without that file.
  List<MaterialRole> get unmetRequirements {
    if (targetKind != IntakeTargetKind.create) return const [];
    final present = includedFiles.map((file) => file.effectiveRole).toSet();
    return missingRequiredRolesIfNew
        .where((role) => !present.contains(role))
        .toList();
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
    missingRequiredRolesIfNew: missingRequiredRolesIfNew,
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

  /// Files a classification call would still be spent on.
  ///
  /// Excludes anything the reviewer already excluded or decided themselves --
  /// paying to classify a file nobody will import, or one whose role is
  /// already chosen, is money spent on a question with no consequence.
  List<IntakeFileState> get pendingClassification => allFiles
      .where(
        (file) =>
            file.needsClassification &&
            !file.excluded &&
            file.humanRole == null &&
            file.proposedRole == null &&
            !file.proposalConfirmed,
      )
      .toList();

  /// Proposals the reviewer has not looked at yet.
  ///
  /// While this is non-empty the batch cannot be imported. Not a warning: the
  /// import action is unavailable.
  List<IntakeFileState> get unconfirmedProposals =>
      allFiles.where((file) => file.blocksImport).toList();

  /// Whether the batch can be imported at all.
  bool get canImport =>
      groups.isNotEmpty &&
      groups.any((group) => group.includedFiles.isNotEmpty) &&
      groups.every((group) => group.includedFiles.isEmpty || group.isReady);

  /// Estimated cost of [pendingClassification], or `null` when no unit price
  /// has been entered -- in which case the screen says the price is unknown
  /// rather than printing a zero that looks like "free".
  double? get estimatedCost =>
      unitCost == null ? null : unitCost! * pendingClassification.length;

  IntakeReviewState copyWith({
    List<IntakeGroupState>? groups,
    double? unitCost,
  }) => IntakeReviewState(
    groups: groups ?? this.groups,
    unitCost: unitCost ?? this.unitCost,
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

  IntakeReviewState withGroup(
    String key,
    IntakeGroupState Function(IntakeGroupState) update,
  ) => copyWith(
    groups: [
      for (final group in groups) group.key == key ? update(group) : group,
    ],
  );
}

/// Build the initial review state from a sidecar plan and the scan it came
/// from.
///
/// The scan is needed because the plan deliberately carries no absolute paths
/// -- it was built from a listing, and the files themselves never left the
/// machine.
IntakeReviewState buildReviewState({
  required IntakePlanResponse plan,
  required ScannedFolder folder,
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
          missingRequiredRolesIfNew: group.missingRequiredRolesIfNew.toList(),
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
