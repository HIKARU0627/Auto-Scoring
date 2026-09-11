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
  answerDetectionZeroResults: requirement(
    "answer-detection-zero-results",
    "自動検出は終わりましたが、回答欄が1件も見つかりませんでした。「領域を手動追加」で枠を引くか、別の答案を選んで再度検出してください。",
  ),
  answerSheetRoleMismatch: requirement(
    "answer-sheet-role-mismatch",
    "この答案では設問に対応する回答欄が見つかりませんでした。取り込んだ PDF が答案用紙か確認し、違う資料なら「別の答案に差し替える」で選び直してください。",
  ),
  answerDetectionRateLimited: (seconds: number | null): ActionRequirement => {
    const wait =
      seconds === null ? "少し待って" : `約${Math.ceil(seconds)}秒待って`;
    return requirement(
      "answer-detection-rate-limited",
      `いま AI が混み合っていて、回答欄を検出できませんでした。${wait}から、もう一度「回答欄を自動検出」を押してください。`,
    );
  },
  answerDetectionUnavailable: requirement(
    "answer-detection-unavailable",
    "この端末では回答欄の自動検出が使えません。設定を確認するか「領域を手動追加」で引いてください。",
  ),
  answerDetectCriteriaUnconfirmed: requirement(
    "answer-detect-criteria-unconfirmed",
    "先に配点と採点基準を確定してください。検出した回答欄は設問に割り当てます。",
  ),
  answerDetectLayoutMissing: requirement(
    "answer-detect-layout-missing",
    "答案がまだ登録されていません。「回答欄を決める答案を選ぶ」でこの様式の答案を1枚登録してください。",
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
  dependencyGraphMissing: requirement(
    "dependency-graph-missing",
    "設問依存関係グラフがまだありません。「依存関係を分析」を押してください。",
  ),
  dependencyGraphAlreadyConfirmed: requirement(
    "dependency-graph-already-confirmed",
    "設問依存関係グラフは確定済みです。",
  ),
  criteriaUnconfirmed: requirement(
    "criteria-unconfirmed",
    "配点と採点基準が未確定です。上の「配点」で確定してください。",
  ),
  profileUnconfirmed: requirement(
    "profile-unconfirmed",
    "回答欄（テストプロファイル）が未確定です。上の「プロファイルを確定」を押してください。",
  ),
  dependencyGraphUnconfirmed: requirement(
    "dependency-graph-unconfirmed",
    "設問依存関係グラフが未確定です。上の「依存関係グラフを確定」を押してください。",
  ),
  dependencyGraphStale: requirement(
    "dependency-graph-stale",
    "設問が変わったため、設問依存関係グラフを分析し直して確定してください。このまま「登録完了」を押すと断られます。",
  ),
  registrationAlreadyComplete: requirement(
    "registration-already-complete",
    "登録は完了しています。答案を取り込むと採点が始まります。",
  ),
  answersDeferredUntilRegistered: requirement(
    "answers-deferred-until-registered",
    "このテストはまだ登録が済んでいないので、答案はこのあと取り込みます。",
  ),
  submissionTestNotReady: requirement(
    "submission-test-not-ready",
    "このテストはまだ登録が済んでいないため、答案を取り込めません。先に登録を完了してから、同じフォルダをもう一度取り込んでください。",
  ),
  submissionDuplicate: requirement(
    "submission-duplicate",
    "同じ答案がすでに取り込まれています。取り込み直す必要はありません。",
  ),
  submissionRetryConflict: requirement(
    "submission-retry-conflict",
    "この答案はほかの操作で再取り込み中です。少し待ってからもう一度取り込んでください。",
  ),
  submissionRejected: requirement(
    "submission-rejected",
    "この答案ファイルは取り込めませんでした。PDFかどうか、暗号化されていないかを確認してください。",
  ),
  submissionServerError: requirement(
    "submission-server-error",
    "一時的な問題で答案を取り込めませんでした。時間をおいてもう一度取り込んでください。",
  ),
  submissionConfirmReady: (pending: number): ActionRequirement =>
    requirement(
      "submission-confirm-ready",
      `全設問の判断材料を表示しました。${pending}問をまとめて確定できます。`,
    ),
  submissionConfirmNoQuestions: requirement(
    "submission-confirm-no-questions",
    "このテストには設問が登録されていません。",
  ),
  submissionConfirmMaterialUnavailable: (
    numbers: string | number,
  ): ActionRequirement =>
    requirement(
      "submission-confirm-material-unavailable",
      `判断材料を読み込めていない設問があります（${numbers}）。再読み込みしてください。`,
    ),
  submissionConfirmHumanScoreRequired: (
    numbers: string | number,
  ): ActionRequirement =>
    requirement(
      "submission-confirm-human-score-required",
      `AIが採点できなかった設問があります（${numbers}）。その設問を開いて点数を入力すると、まとめて確定できます。`,
    ),
  submissionConfirmUnreached: (
    numbers: string | number,
    unreadIsAbove = false,
  ): ActionRequirement =>
    requirement(
      "submission-confirm-unreached",
      `まだ表示していない設問があります（${numbers}）。${unreadIsAbove ? "上" : "下"}方向へスクロールすると確定できます。`,
    ),
  submissionConfirmNothingToConfirm: requirement(
    "submission-confirm-nothing-to-confirm",
    "この答案は全設問を確定済みです。",
  ),
  answerAreaUndetected: (count: number): ActionRequirement =>
    requirement(
      "answer-area-undetected",
      `回答欄が見つからなかった設問が${count}件あります。このまま確定もできますが、その設問は答案のページ全体を採点に送り、要確認として人の目に回ります。`,
    ),
  answerAreaUndetectedAction: requirement(
    "answer-area-undetected-action",
    "答案には回答欄があるはずです。設問名を押して枠を引いてください。",
  ),
  answerAreaAbsent: (count: number): ActionRequirement =>
    requirement(
      "answer-area-absent",
      `この答案では回答欄を見つけられなかった設問が${count}件あります。登録した答案が課題の一部のページで、採点基準がそれより広い範囲を含んでいることがあります。まず答案と採点基準を確かめてください。`,
    ),
  answerAreaAbsentAction: requirement(
    "answer-area-absent-action",
    "答案に回答欄があるのに挙がっているときは、設問名を押して枠を引いてください。",
  ),
  profileConfirmUndetected: (count: number): ActionRequirement =>
    requirement(
      "profile-confirm-undetected",
      `回答欄が見つかっていない設問が${count}件あります。このまま確定すると、その設問は答案のページ全体を採点に送り、要確認として人の目に回ります。`,
    ),
  profileConfirmUndetectedAction: requirement(
    "profile-confirm-undetected-action",
    "設問名を押して枠を引くか、内容を確かめたうえで確定してください。",
  ),
  answerCoverageIncomplete: (
    expected: number,
    covered: number,
    uncovered: number,
  ): ActionRequirement =>
    requirement(
      "answer-coverage-incomplete",
      `採点基準の設問は${expected}件、登録済み答案で回答欄が覆えているのは${covered}件です。覆えていない設問が${uncovered}件あります。`,
    ),
  answerCoverageComplete: (covered: number): ActionRequirement =>
    requirement(
      "answer-coverage-complete",
      `採点基準の設問${covered}件すべてに回答欄があります。`,
    ),
  gradingInProgress: requirement(
    "grading-in-progress",
    "AIが採点中です。採点が終わると承認できます。",
  ),
  bulkExportDestinationUnavailable: requirement(
    "bulk-export-destination-unavailable",
    "この端末では保存先フォルダを選ぶ手段がありません。アプリを再起動してから、もう一度お試しください。",
  ),
  gradingStatusStale: requirement(
    "grading-status-stale",
    "AI採点の状況を自動で更新できませんでした。「再読み込み」を押して最新の状態を確認してください。",
  ),
} as const;

/** 答案の取込が失敗したときの種類。`createSubmission` が返す区分。 */
export type SubmissionImportFailureKind =
  "not-ready" | "retry-conflict" | "rejected" | "server";

/** 失敗の種類ごとに、画面へ出す理由文を 1 箇所から返す (INV-004)。 */
export function submissionImportFailureRequirement(
  kind: SubmissionImportFailureKind,
): ActionRequirement {
  switch (kind) {
    case "not-ready":
      return ActionRequirements.submissionTestNotReady;
    case "retry-conflict":
      return ActionRequirements.submissionRetryConflict;
    case "rejected":
      return ActionRequirements.submissionRejected;
    case "server":
      return ActionRequirements.submissionServerError;
  }
}

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

/** 検出が 0 件で終わったときに出す結果の説明 */
export function answerDetectionOutcomeRequirements(input: {
  outcome: "none" | "zero-results" | "role-mismatch" | "rate-limited";
  retryAfterSeconds?: number | null;
}): readonly ActionRequirement[] {
  if (input.outcome === "zero-results") {
    return [ActionRequirements.answerDetectionZeroResults];
  }
  if (input.outcome === "role-mismatch") {
    return [ActionRequirements.answerSheetRoleMismatch];
  }
  if (input.outcome === "rate-limited") {
    return [
      ActionRequirements.answerDetectionRateLimited(
        input.retryAfterSeconds ?? null,
      ),
    ];
  }
  return [];
}

/** テスト設定の「回答欄を自動検出」 */
export function answerDetectRequirements(input: {
  busy: boolean;
  alreadyConfirmed: boolean;
  answerSheetRegistered: boolean;
  detectionAvailable: boolean;
  criteriaConfirmed: boolean;
}): readonly ActionRequirement[] {
  const requirements: ActionRequirement[] = [];
  if (input.busy) {
    requirements.push(ActionRequirements.busy);
  }
  if (input.alreadyConfirmed) {
    requirements.push(ActionRequirements.profileAlreadyConfirmed);
  }
  if (!input.criteriaConfirmed) {
    requirements.push(ActionRequirements.answerDetectCriteriaUnconfirmed);
  }
  if (!input.answerSheetRegistered) {
    requirements.push(ActionRequirements.answerDetectLayoutMissing);
  }
  if (!input.detectionAvailable) {
    requirements.push(ActionRequirements.answerDetectionUnavailable);
  }
  return requirements;
}

/** テスト設定の「領域を手動追加」 */
export function answerRegionAddRequirements(input: {
  busy: boolean;
  alreadyConfirmed: boolean;
  answerSheetRegistered: boolean;
}): readonly ActionRequirement[] {
  const requirements: ActionRequirement[] = [];
  if (input.busy) {
    requirements.push(ActionRequirements.busy);
  }
  if (input.alreadyConfirmed) {
    requirements.push(ActionRequirements.profileAlreadyConfirmed);
  }
  if (!input.answerSheetRegistered) {
    requirements.push(ActionRequirements.answerSheetUnseen);
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

/** テスト設定の「依存関係グラフを確定」 */
export function dependencyGraphConfirmRequirements(input: {
  busy: boolean;
  hasGraph: boolean;
  alreadyConfirmed: boolean;
}): readonly ActionRequirement[] {
  const requirements: ActionRequirement[] = [];
  if (input.busy) {
    requirements.push(ActionRequirements.busy);
  }
  if (input.alreadyConfirmed) {
    requirements.push(ActionRequirements.dependencyGraphAlreadyConfirmed);
  }
  if (!input.hasGraph) {
    requirements.push(ActionRequirements.dependencyGraphMissing);
  }
  return requirements;
}

/** テスト設定の「登録完了」 */
export function completeRegistrationRequirements(input: {
  busy: boolean;
  alreadyComplete: boolean;
  profileConfirmed: boolean;
  dependencyGraphConfirmed: boolean;
}): readonly ActionRequirement[] {
  const requirements: ActionRequirement[] = [];
  if (input.busy) {
    requirements.push(ActionRequirements.busy);
  }
  if (input.alreadyComplete) {
    requirements.push(ActionRequirements.registrationAlreadyComplete);
  }
  if (!input.profileConfirmed) {
    requirements.push(ActionRequirements.profileUnconfirmed);
  }
  if (!input.dependencyGraphConfirmed) {
    requirements.push(ActionRequirements.dependencyGraphUnconfirmed);
  }
  return requirements;
}

/** 採点が始まるまでにテスト設定で残っていること */
export function gradingStartRequirements(input: {
  criteriaSettled: boolean;
  profileConfirmed: boolean;
  dependencyGraphConfirmed: boolean;
  dependencyGraphStale: boolean;
}): readonly ActionRequirement[] {
  const requirements: ActionRequirement[] = [];
  if (!input.criteriaSettled) {
    requirements.push(ActionRequirements.criteriaUnconfirmed);
  }
  if (!input.profileConfirmed) {
    requirements.push(ActionRequirements.profileUnconfirmed);
  }
  if (!input.dependencyGraphConfirmed) {
    requirements.push(ActionRequirements.dependencyGraphUnconfirmed);
  } else if (input.dependencyGraphStale) {
    requirements.push(ActionRequirements.dependencyGraphStale);
  }
  return requirements;
}

/**
 * 未検出の設問が残ったままプロファイルを確定しようとしたときの確認 (Issue #314).
 *
 * The list is deliberately separate from `answerProfileConfirmRequirements`:
 * that function drives the confirm button's disabled state, and an undetected
 * question must not disable it -- it must open a confirmation that names the
 * count, so a partial registration cannot be signed off without the reviewer
 * seeing what is uncovered.
 */
export function answerProfileUndetectedConfirmRequirements(input: {
  undetectedQuestionCount: number;
}): readonly ActionRequirement[] {
  if (input.undetectedQuestionCount <= 0) {
    return [];
  }
  return [
    ActionRequirements.profileConfirmUndetected(input.undetectedQuestionCount),
  ];
}

/**
 * 登録済み答案が採点基準の設問をどれだけ覆えているか (Issue #314).
 *
 * `uncovered` counts every criteria question with no `answer_area` region,
 * whether detection declared it absent from the sheet or simply never found a
 * box for it: either way the registered pages do not cover that question.
 */
export function answerCoverageRequirements(input: {
  expected: number;
  covered: number;
}): readonly ActionRequirement[] {
  if (input.expected <= 0) {
    return [];
  }
  if (input.covered >= input.expected) {
    return [ActionRequirements.answerCoverageComplete(input.expected)];
  }
  return [
    ActionRequirements.answerCoverageIncomplete(
      input.expected,
      input.covered,
      input.expected - input.covered,
    ),
  ];
}

/**
 * 添削レビュー画面で「承認」が押せない理由 (Issue #319).
 *
 * Approve is disabled both while this screen is busy and while the selected
 * question's grading job has not reached a terminal state. The second case is
 * the one that stranded reviewers: the home screen sends them into review
 * before grading finishes, and the screen said nothing about why the button
 * was dead. Keeping that sentence here (rather than in the feature) is what
 * INV-004 requires.
 */
export function reviewApproveRequirements(input: {
  busy: boolean;
  gradingInProgress: boolean;
}): readonly ActionRequirement[] {
  const requirements: ActionRequirement[] = [];
  if (input.busy) {
    requirements.push(ActionRequirements.busy);
  }
  if (input.gradingInProgress) {
    requirements.push(ActionRequirements.gradingInProgress);
  }
  return requirements;
}
