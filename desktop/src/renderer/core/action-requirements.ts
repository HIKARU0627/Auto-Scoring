/**
 * Action requirement messages for disabled controls (Issue #88).
 *
 * Wording lives here only — screens count conditions and display these messages.
 */

export interface ActionRequirement {
  readonly id: string;
  readonly message: string;
}

function requirement(id: string, message: string): ActionRequirement {
  return { id, message };
}

export const ActionRequirements = {
  busy: requirement("busy", "この画面の処理が終わるまで待ってください。"),
  intakeTemplate: requirement(
    "intake-template",
    "上の「取込の型」で、どの型で振り分けるかを選んでください。",
  ),
  intakeNothingToImport: requirement(
    "intake-nothing-to-import",
    "取り込むファイルが1件もありません。除外を外すか、別のフォルダを選び直してください。",
  ),
  intakeTargetUnassigned: (groups: number): ActionRequirement =>
    requirement(
      "intake-target-unassigned",
      `取込先が決まっていないフォルダが${groups}件あります。各フォルダの取り込み先を選んでください。`,
    ),
  intakeTestNameEmpty: (groups: number): ActionRequirement =>
    requirement(
      "intake-test-name-empty",
      `新しいテストを作るフォルダのうち${groups}件に名前がありません。テスト名を入力してください。`,
    ),
  intakeRequiredRoleMissing: (roles: number): ActionRequirement =>
    requirement(
      "intake-required-role-missing",
      `新しいテストに必要な役割の資料が${roles}件足りません。不足している役割のファイルを追加するか、取り込み先を変えてください。`,
    ),
  intakeProposalUnconfirmed: (files: number): ActionRequirement =>
    requirement(
      "intake-proposal-unconfirmed",
      `AIの提案を${files}件まだ確認していません。内容を確かめてから取り込んでください。`,
    ),
  intakeAnswerUnrouted: (files: number): ActionRequirement =>
    requirement(
      "intake-answer-unrouted",
      `どのテストの答案か決まっていないファイルが${files}件あります。振り分け先を選んでください。`,
    ),
  intakeNonAnswerUnroutable: (files: number): ActionRequirement =>
    requirement(
      "intake-non-answer-unroutable",
      `答案ごとに振り分けるフォルダに、答案以外のファイルが${files}件あります。除外するか、取り込み先を1つのテストに変えてください。`,
    ),
} as const;

export function intakeFolderPickRequirements(input: {
  busy: boolean;
  templateChosen: boolean;
}): readonly ActionRequirement[] {
  const requirements: ActionRequirement[] = [];
  if (input.busy) {
    requirements.push(ActionRequirements.busy);
  }
  if (!input.templateChosen) {
    requirements.push(ActionRequirements.intakeTemplate);
  }
  return requirements;
}

export function intakeImportRequirements(input: {
  busy: boolean;
  classifying: boolean;
  folderRequirements: readonly ActionRequirement[];
}): readonly ActionRequirement[] {
  const requirements: ActionRequirement[] = [];
  if (input.busy || input.classifying) {
    requirements.push(ActionRequirements.busy);
  }
  return [...requirements, ...input.folderRequirements];
}
