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
  credentialStoreUnavailable: requirement(
    "credential-store-unavailable",
    "この PC の資格情報ストアが使えないため、キーを保存できません。上の通知にある理由を解消するか、環境変数でキーを渡してください。",
  ),
  apiKeyNotConfigured: requirement(
    "api-key-not-configured",
    "キーがまだありません。上の欄に入力して「保存する」を押すと疎通を確認できます。",
  ),
  answerRegionsMissing: requirement(
    "answer-regions-missing",
    "回答欄が1つもありません。「回答欄を自動検出」するか「領域を手動追加」で引いてください。",
  ),
  answerRegionsUnassigned: (regions: number): ActionRequirement =>
    requirement(
      "answer-regions-unassigned",
      `設問が割り当てられていない回答欄が${regions}件あります。設問を選ぶか削除してください。`,
    ),
  answerSheetUnseen: requirement(
    "answer-sheet-unseen",
    "回答欄の位置は答案の上で確認します。この様式の答案を1枚登録してください。",
  ),
  answerSheetUnrendered: requirement(
    "answer-sheet-unrendered",
    "答案を表示できていません。上の「再試行」を押して、実際の答案を出してください。",
  ),
  profileAlreadyConfirmed: requirement(
    "profile-already-confirmed",
    "テストプロファイルは確定済みです。確定した回答欄は変更できません。",
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

/** 進行中の処理が終わるまでしか無効にならない操作 */
export function whileRunningRequirements(input: {
  running: boolean;
}): readonly ActionRequirement[] {
  if (input.running) {
    return [ActionRequirements.busy];
  }
  return [];
}

/** 設定画面 API キータブの「保存する」 */
export function apiKeySaveRequirements(input: {
  busy: boolean;
  credentialStoreAvailable: boolean;
}): readonly ActionRequirement[] {
  const requirements: ActionRequirement[] = [];
  if (input.busy) {
    requirements.push(ActionRequirements.busy);
  }
  if (!input.credentialStoreAvailable) {
    requirements.push(ActionRequirements.credentialStoreUnavailable);
  }
  return requirements;
}

/** 設定画面 API キータブの「疎通を確認する」 (INV-107) */
export function apiKeyVerifyRequirements(input: {
  busy: boolean;
  configured: boolean;
}): readonly ActionRequirement[] {
  const requirements: ActionRequirement[] = [];
  if (input.busy) {
    requirements.push(ActionRequirements.busy);
  }
  if (!input.configured) {
    requirements.push(ActionRequirements.apiKeyNotConfigured);
  }
  return requirements;
}

/** テスト設定の「修正内容を保存」 */
export function answerProfileSaveRequirements(input: {
  busy: boolean;
  hasRegions: boolean;
  alreadyConfirmed: boolean;
}): readonly ActionRequirement[] {
  const requirements: ActionRequirement[] = [];
  if (input.busy) {
    requirements.push(ActionRequirements.busy);
  }
  if (input.alreadyConfirmed) {
    requirements.push(ActionRequirements.profileAlreadyConfirmed);
  }
  if (!input.hasRegions) {
    requirements.push(ActionRequirements.answerRegionsMissing);
  }
  return requirements;
}

/** テスト設定の「プロファイルを確定」 (INV-110) */
export function answerProfileConfirmRequirements(input: {
  busy: boolean;
  alreadyConfirmed: boolean;
  regionCount: number;
  unassignedRegionCount: number;
  mustSeeAnswerSheetFirst: boolean;
  answerSheetRegistered: boolean;
}): readonly ActionRequirement[] {
  const requirements: ActionRequirement[] = [];
  if (input.busy) {
    requirements.push(ActionRequirements.busy);
  }
  if (input.alreadyConfirmed) {
    requirements.push(ActionRequirements.profileAlreadyConfirmed);
  }
  if (input.regionCount === 0) {
    requirements.push(ActionRequirements.answerRegionsMissing);
  }
  if (input.unassignedRegionCount > 0) {
    requirements.push(
      ActionRequirements.answerRegionsUnassigned(input.unassignedRegionCount),
    );
  }
  if (input.mustSeeAnswerSheetFirst) {
    requirements.push(
      input.answerSheetRegistered
        ? ActionRequirements.answerSheetUnrendered
        : ActionRequirements.answerSheetUnseen,
    );
  }
  return requirements;
}
