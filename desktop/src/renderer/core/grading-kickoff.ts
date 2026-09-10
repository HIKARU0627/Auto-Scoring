export interface GradingKickoffFailure {
  readonly message: string;
  readonly retryable: boolean;
}

export function gradingKickoffFailureFromStatus(
  statusCode: number,
): GradingKickoffFailure {
  if (statusCode === 404) {
    return {
      message: "この答案が見つかりません。AI採点を開始できません。",
      retryable: false,
    };
  }
  if (statusCode === 409) {
    return {
      message:
        "AI採点を開始できませんでした。テストの設問依存関係が確定していないか、" +
        "ほかの操作と競合しています。テスト設定で依存関係を確定してから、" +
        "時間をおいて再試行してください。",
      retryable: true,
    };
  }
  return {
    message: "AI採点を開始できませんでした。時間をおいて再試行してください。",
    retryable: true,
  };
}
