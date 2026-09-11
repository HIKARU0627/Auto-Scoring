import type { components } from "../api/generated/schema.js";
import type { ScannedFolder } from "../../shared/folder-scan.js";
import {
  ActionRequirements,
  type ActionRequirement,
} from "./action-requirements.js";

export type MaterialRole = components["schemas"]["MaterialRole"];
export type IntakePlanResponse = components["schemas"]["IntakePlanResponse"];
export type IntakeTemplateModel = components["schemas"]["IntakeTemplateModel"];

export enum IntakeTargetKind {
  create = "create",
  existing = "existing",
  perAnswer = "perAnswer",
  unassigned = "unassigned",
}

export enum IntakeRoleOrigin {
  rule = "rule",
  proposal = "proposal",
  human = "human",
  unresolved = "unresolved",
}

export interface IntakeFileState {
  readonly relativePath: string;
  readonly absolutePath: string;
  readonly sha256: string;
  readonly sizeBytes: number;
  readonly ruleRole: MaterialRole | null;
  readonly needsClassification: boolean;
  readonly cachedClassification: boolean;
  readonly classificationAttempted: boolean;
  readonly proposedRole: MaterialRole | null;
  readonly proposalConfirmed: boolean;
  readonly humanRole: MaterialRole | null;
  readonly excluded: boolean;
  readonly answerTestId: string | null;
  readonly proposedAnswerTestId: string | null;
  readonly attributionAttempted: boolean;
}

export function intakeFileName(file: IntakeFileState): string {
  const parts = file.relativePath.split("/");
  return parts[parts.length - 1] ?? file.relativePath;
}

export function effectiveRole(file: IntakeFileState): MaterialRole | null {
  return file.humanRole ?? file.ruleRole ?? file.proposedRole;
}

export function roleOrigin(file: IntakeFileState): IntakeRoleOrigin {
  if (file.humanRole !== null) {
    return IntakeRoleOrigin.human;
  }
  if (file.ruleRole !== null) {
    return IntakeRoleOrigin.rule;
  }
  if (file.proposedRole !== null || file.proposalConfirmed) {
    return IntakeRoleOrigin.proposal;
  }
  return IntakeRoleOrigin.unresolved;
}

export function blocksImport(file: IntakeFileState): boolean {
  if (file.excluded) {
    return false;
  }
  if (file.humanRole !== null) {
    return false;
  }
  if (file.ruleRole !== null) {
    return false;
  }
  return !file.proposalConfirmed || effectiveRole(file) === null;
}

export function copyIntakeFile(
  file: IntakeFileState,
  patch: Partial<IntakeFileState>,
): IntakeFileState {
  return { ...file, ...patch };
}

export interface IntakeBlockingCounts {
  readonly targetUnassigned: number;
  readonly requiredRolesMissing: number;
  readonly testNameEmpty: number;
  readonly answersUnrouted: number;
  readonly nonAnswersUnroutable: number;
  readonly unconfirmedProposals: number;
}

function emptyBlockingCounts(): IntakeBlockingCounts {
  return {
    targetUnassigned: 0,
    requiredRolesMissing: 0,
    testNameEmpty: 0,
    answersUnrouted: 0,
    nonAnswersUnroutable: 0,
    unconfirmedProposals: 0,
  };
}

function isBlockingClear(counts: IntakeBlockingCounts): boolean {
  return (
    counts.targetUnassigned === 0 &&
    counts.requiredRolesMissing === 0 &&
    counts.testNameEmpty === 0 &&
    counts.answersUnrouted === 0 &&
    counts.nonAnswersUnroutable === 0 &&
    counts.unconfirmedProposals === 0
  );
}

function plusBlockingCounts(
  a: IntakeBlockingCounts,
  b: IntakeBlockingCounts,
): IntakeBlockingCounts {
  return {
    targetUnassigned: a.targetUnassigned + b.targetUnassigned,
    requiredRolesMissing: a.requiredRolesMissing + b.requiredRolesMissing,
    testNameEmpty: a.testNameEmpty + b.testNameEmpty,
    answersUnrouted: a.answersUnrouted + b.answersUnrouted,
    nonAnswersUnroutable: a.nonAnswersUnroutable + b.nonAnswersUnroutable,
    unconfirmedProposals: a.unconfirmedProposals + b.unconfirmedProposals,
  };
}

function blockingRequirements(
  counts: IntakeBlockingCounts,
): readonly ActionRequirement[] {
  const requirements: ActionRequirement[] = [];
  if (counts.targetUnassigned > 0) {
    requirements.push(
      ActionRequirements.intakeTargetUnassigned(counts.targetUnassigned),
    );
  }
  if (counts.testNameEmpty > 0) {
    requirements.push(
      ActionRequirements.intakeTestNameEmpty(counts.testNameEmpty),
    );
  }
  if (counts.requiredRolesMissing > 0) {
    requirements.push(
      ActionRequirements.intakeRequiredRoleMissing(counts.requiredRolesMissing),
    );
  }
  if (counts.unconfirmedProposals > 0) {
    requirements.push(
      ActionRequirements.intakeProposalUnconfirmed(counts.unconfirmedProposals),
    );
  }
  if (counts.answersUnrouted > 0) {
    requirements.push(
      ActionRequirements.intakeAnswerUnrouted(counts.answersUnrouted),
    );
  }
  if (counts.nonAnswersUnroutable > 0) {
    requirements.push(
      ActionRequirements.intakeNonAnswerUnroutable(counts.nonAnswersUnroutable),
    );
  }
  return requirements;
}

export interface IntakeGroupState {
  readonly key: string;
  readonly name: string;
  readonly files: readonly IntakeFileState[];
  readonly requiredRoles: readonly MaterialRole[];
  readonly targetKind: IntakeTargetKind;
  readonly targetTestId: string | null;
  /**
   * 対象テストの `status`（`TestResponse.status`）。`create` や未割当では `null`。
   * 答案を取り込む段かどうかは、画面の状態変数ではなくこの値から機械的に決める
   * （Issue #306 案 A）。`ready` だけが答案を受け付ける。
   */
  readonly targetTestStatus: string | null;
}

/**
 * 対象テストが答案を受け付けるか。バックエンドの `TestNotReadyError`（409）と
 * 同じ規則を 1 箇所に固定する。
 */
export function targetTestAcceptsAnswers(
  status: string | null | undefined,
): boolean {
  return status === "ready";
}

export type ReusableTest = {
  readonly id: string;
  readonly name: string;
  readonly status: string;
  readonly created_at: string;
};

/**
 * 同じ名前の既存テストを探す（Issue #306 の再利用規則）。
 *
 * グループ名は取り込みプランがフォルダの第 1 階層から作る `suggested_name` で、
 * テスト名もこれで登録される。同じフォルダを再度取り込んだときは、まず同じ名前の
 * `ready` なテストを再利用する（`ready` が無ければ同じ名前の `draft`、それも無ければ
 * 直近のもの）。名前を唯一の手掛かりにするのは、フォルダ側にそれ以外の永続的な
 * 識別子が無いため。名前変更や同名テストの併存は再利用の対象外になる。
 */
export function findReusableTest<T extends ReusableTest>(
  existingTests: readonly T[],
  name: string,
): T | undefined {
  const wanted = name.trim();
  if (wanted.length === 0) {
    return undefined;
  }
  const matches = existingTests.filter((test) => test.name.trim() === wanted);
  if (matches.length === 0) {
    return undefined;
  }
  const ready = matches.filter((test) => test.status === "ready");
  const pool = ready.length > 0 ? ready : matches;
  return [...pool].sort(
    (a, b) => Date.parse(b.created_at) - Date.parse(a.created_at),
  )[0];
}

export function includedFiles(
  group: IntakeGroupState,
): readonly IntakeFileState[] {
  return group.files.filter((file) => !file.excluded);
}

export function unmetRequirements(
  group: IntakeGroupState,
): readonly MaterialRole[] {
  if (group.targetKind !== IntakeTargetKind.create) {
    return [];
  }
  const present = new Set(
    includedFiles(group).map((file) => effectiveRole(file)),
  );
  return group.requiredRoles.filter((role) => !present.has(role));
}

export function unroutedAnswers(
  group: IntakeGroupState,
): readonly IntakeFileState[] {
  if (group.targetKind !== IntakeTargetKind.perAnswer) {
    return [];
  }
  return includedFiles(group).filter(
    (file) =>
      effectiveRole(file) === "student_answer" && file.answerTestId === null,
  );
}

export function unconfirmedAttributions(
  group: IntakeGroupState,
): readonly IntakeFileState[] {
  if (group.targetKind !== IntakeTargetKind.perAnswer) {
    return [];
  }
  return unroutedAnswers(group).filter(
    (file) => file.proposedAnswerTestId !== null,
  );
}

export function unroutableNonAnswers(
  group: IntakeGroupState,
): readonly IntakeFileState[] {
  if (group.targetKind !== IntakeTargetKind.perAnswer) {
    return [];
  }
  return includedFiles(group).filter(
    (file) => effectiveRole(file) !== "student_answer",
  );
}

export function groupBlockingCounts(
  group: IntakeGroupState,
): IntakeBlockingCounts {
  return {
    targetUnassigned: group.targetKind === IntakeTargetKind.unassigned ? 1 : 0,
    requiredRolesMissing: unmetRequirements(group).length,
    testNameEmpty:
      group.targetKind === IntakeTargetKind.create &&
      group.name.trim().length === 0
        ? 1
        : 0,
    answersUnrouted: unroutedAnswers(group).length,
    nonAnswersUnroutable: unroutableNonAnswers(group).length,
    unconfirmedProposals: includedFiles(group).filter((file) =>
      blocksImport(file),
    ).length,
  };
}

export function groupIsReady(group: IntakeGroupState): boolean {
  if (includedFiles(group).length === 0) {
    return false;
  }
  return isBlockingClear(groupBlockingCounts(group));
}

export function copyIntakeGroup(
  group: IntakeGroupState,
  patch: Partial<IntakeGroupState>,
): IntakeGroupState {
  return { ...group, ...patch };
}

export interface IntakeReviewState {
  readonly groups: readonly IntakeGroupState[];
  readonly unitCost: number | null;
}

export function allFiles(
  review: IntakeReviewState,
): readonly IntakeFileState[] {
  return review.groups.flatMap((group) => group.files);
}

export function classifiableFiles(
  review: IntakeReviewState,
): readonly IntakeFileState[] {
  return allFiles(review).filter(
    (file) =>
      (file.needsClassification || file.cachedClassification) &&
      !file.classificationAttempted &&
      !file.excluded &&
      file.humanRole === null &&
      file.proposedRole === null &&
      !file.proposalConfirmed,
  );
}

export function pendingClassification(
  review: IntakeReviewState,
): readonly IntakeFileState[] {
  return allFiles(review).filter(
    (file) =>
      file.needsClassification &&
      !file.classificationAttempted &&
      !file.excluded &&
      file.humanRole === null &&
      file.proposedRole === null &&
      !file.proposalConfirmed,
  );
}

export function unconfirmedProposals(
  review: IntakeReviewState,
): readonly IntakeFileState[] {
  const roleProposals = allFiles(review).filter((file) => blocksImport(file));
  const attributionProposals = review.groups.flatMap((group) =>
    unconfirmedAttributions(group),
  );
  return [...roleProposals, ...attributionProposals];
}

export function importRequirements(
  review: IntakeReviewState,
): readonly ActionRequirement[] {
  const active = review.groups.filter(
    (group) => includedFiles(group).length > 0,
  );
  if (active.length === 0) {
    return [ActionRequirements.intakeNothingToImport];
  }
  const totals = active
    .map((group) => groupBlockingCounts(group))
    .reduce(plusBlockingCounts, emptyBlockingCounts());
  return blockingRequirements(totals);
}

export function canImport(review: IntakeReviewState): boolean {
  return importRequirements(review).length === 0;
}

export function answersNeedingAttribution(
  review: IntakeReviewState,
): readonly IntakeFileState[] {
  const answers: IntakeFileState[] = [];
  for (const group of review.groups) {
    if (group.targetKind !== IntakeTargetKind.perAnswer) {
      continue;
    }
    for (const answer of unroutedAnswers(group)) {
      if (!answer.attributionAttempted) {
        answers.push(answer);
      }
    }
  }
  return answers;
}

export function estimatedCostForCalls(
  review: IntakeReviewState,
  calls: number,
): number | null {
  if (review.unitCost === null) {
    return null;
  }
  return review.unitCost * calls;
}

export function withFile(
  review: IntakeReviewState,
  relativePath: string,
  update: (file: IntakeFileState) => IntakeFileState,
): IntakeReviewState {
  return {
    ...review,
    groups: review.groups.map((group) =>
      copyIntakeGroup(group, {
        files: group.files.map((file) =>
          file.relativePath === relativePath ? update(file) : file,
        ),
      }),
    ),
  };
}

export function withGroup(
  review: IntakeReviewState,
  key: string,
  update: (group: IntakeGroupState) => IntakeGroupState,
): IntakeReviewState {
  return {
    ...review,
    groups: review.groups.map((group) =>
      group.key === key ? update(group) : group,
    ),
  };
}

export function confirmAllProposals(
  review: IntakeReviewState,
): IntakeReviewState {
  return {
    ...review,
    groups: review.groups.map((group) =>
      copyIntakeGroup(group, {
        files: group.files.map((file) => {
          if (file.excluded) {
            return file;
          }
          return copyIntakeFile(file, {
            proposalConfirmed:
              file.proposedRole !== null ? true : file.proposalConfirmed,
            answerTestId:
              group.targetKind === IntakeTargetKind.perAnswer &&
              file.answerTestId === null
                ? file.proposedAnswerTestId
                : file.answerTestId,
          });
        }),
      }),
    ),
  };
}

export function confirmableProposals(
  review: IntakeReviewState,
): readonly IntakeFileState[] {
  const roleProposals = allFiles(review).filter(
    (file) =>
      !file.excluded &&
      file.proposedRole !== null &&
      !file.proposalConfirmed &&
      file.humanRole === null,
  );
  const attributionProposals = review.groups.flatMap((group) =>
    unconfirmedAttributions(group),
  );
  return [...roleProposals, ...attributionProposals];
}

export function requiredRolesOf(
  templates: readonly IntakeTemplateModel[],
  templateId: string,
): readonly MaterialRole[] {
  const template = templates.find((entry) => entry.id === templateId);
  if (template === undefined) {
    return [];
  }
  const roles: MaterialRole[] = [];
  for (const rule of template.rules) {
    if (rule.requirement === "required" && !roles.includes(rule.role)) {
      roles.push(rule.role);
    }
  }
  return roles;
}

export function pruneStaleTargets(
  review: IntakeReviewState,
  knownTestIds: ReadonlySet<string>,
): IntakeReviewState {
  return {
    ...review,
    groups: review.groups.map((group) => {
      if (
        group.targetKind === IntakeTargetKind.existing &&
        (group.targetTestId === null || !knownTestIds.has(group.targetTestId))
      ) {
        return copyIntakeGroup(group, {
          targetKind: IntakeTargetKind.unassigned,
          targetTestId: null,
          targetTestStatus: null,
        });
      }
      if (
        group.targetKind === IntakeTargetKind.perAnswer &&
        knownTestIds.size === 0
      ) {
        return copyIntakeGroup(group, {
          targetKind: IntakeTargetKind.unassigned,
          targetTestStatus: null,
        });
      }
      return group;
    }),
  };
}

export function buildReviewState(input: {
  plan: IntakePlanResponse;
  folder: ScannedFolder;
  requiredRoles: readonly MaterialRole[];
  unitCost: number | null;
  existingTests?: readonly ReusableTest[];
}): IntakeReviewState {
  const byPath = new Map(
    input.folder.entries.map((entry) => [entry.relativePath, entry]),
  );
  return {
    unitCost: input.unitCost,
    groups: input.plan.groups.map((group) => {
      const reusable = findReusableTest(
        input.existingTests ?? [],
        group.suggested_name,
      );
      return {
        key: group.key,
        name: group.suggested_name,
        requiredRoles: input.requiredRoles,
        targetKind:
          reusable === undefined
            ? IntakeTargetKind.create
            : IntakeTargetKind.existing,
        targetTestId: reusable?.id ?? null,
        targetTestStatus: reusable?.status ?? null,
        files: group.files.map((file) => {
          const scanned = byPath.get(file.relative_path);
          return {
            relativePath: file.relative_path,
            absolutePath: scanned?.absolutePath ?? "",
            sha256: file.sha256,
            sizeBytes: file.size_bytes,
            ruleRole: file.role ?? null,
            needsClassification: file.classification === "pending",
            cachedClassification: file.classification === "cached",
            classificationAttempted: false,
            proposedRole: null,
            proposalConfirmed: false,
            humanRole: null,
            excluded: file.role === "ignore",
            answerTestId: null,
            proposedAnswerTestId: null,
            attributionAttempted: false,
          };
        }),
      };
    }),
  };
}
