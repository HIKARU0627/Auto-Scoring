import { isNotTheAnswerCrop } from "./grading-failure-reason.js";

export interface DagFailureGuidanceText {
  readonly cause: string;
  readonly nextStep: string;
}

export const DagFailureGuidance = {
  answerAreaWrong: {
    cause:
      "AIは、この設問に渡された画像がこの設問の解答ではないと判断しました。",
    nextStep:
      "テスト設定の「回答欄」で、この設問の枠の位置を直してください。位置を直さないまま再判定しても、同じ結果になります。",
  },
  rateLimited: {
    cause: "AIの利用上限に達したため、この設問の処理を打ち切りました。",
    nextStep: "しばらく置いてから「再判定」でやり直せます。",
  },
  temporary: {
    cause: "AIとの通信が最後まで通らず、再試行の上限に達しました。",
    nextStep:
      "「再判定」でもう一度試すか、「点数を入力」で自分で採点できます。",
  },
  permanent: {
    cause:
      "AIはこの設問を処理できませんでした。同じ設定のままでは、やり直しても結果は変わりません。",
    nextStep:
      "テスト設定の教材（模範解答・採点基準）とAIの設定を見直すか、「点数を入力」で自分で採点してください。",
  },
  unknown: {
    cause: "AIはこの設問を処理できませんでした。",
    nextStep:
      "「再判定」でもう一度AIに任せるか、「点数を入力」で自分で採点できます。",
  },
} as const satisfies Record<string, DagFailureGuidanceText>;

export type DagFailureGuidanceKey = keyof typeof DagFailureGuidance;

export function dagFailureGuidance(input: {
  errorCode?: string | null;
  lastError?: string | null;
}): DagFailureGuidanceText {
  if (isNotTheAnswerCrop(input.lastError)) {
    return DagFailureGuidance.answerAreaWrong;
  }
  switch (input.errorCode) {
    case "rate_limited":
      return DagFailureGuidance.rateLimited;
    case "timeout":
    case "server_error":
      return DagFailureGuidance.temporary;
    case "permanent":
      return DagFailureGuidance.permanent;
    default:
      return DagFailureGuidance.unknown;
  }
}
