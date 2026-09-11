import { AppRoutes } from "../core/app-routes.js";
import { matchRoutePattern } from "./router.js";

/**
 * The default heading and one line of context under it for each screen
 * (Issue #335; default heading in Issue #348).
 *
 * A page may still supply its own heading when it is dynamic (a test or answer
 * name); `ShellScreen` falls back to the table here so a screen that forgets
 * one shows the screen name rather than the product name, which the mock
 * already carries in the sidebar (`#333` evaluation A, item 6).
 */
const PAGE_HEADERS: readonly {
  readonly pattern: string;
  readonly title: string;
  readonly subtitle: string;
}[] = [
  { pattern: AppRoutes.home, title: "ホーム", subtitle: "今日もよい添削を" },
  {
    pattern: AppRoutes.intake,
    title: "資料の取込",
    subtitle: "答案と採点資料を取り込んで、テストを準備します",
  },
  {
    pattern: AppRoutes.testList,
    title: "テスト一覧",
    subtitle: "登録したテストと答案の進み具合",
  },
  {
    pattern: AppRoutes.settings,
    title: "設定",
    subtitle: "アプリの設定と資格情報",
  },
  {
    pattern: AppRoutes.testSettingsPattern,
    title: "テスト設定",
    subtitle: "回答欄と設問の依存関係を確認・修正します",
  },
  {
    pattern: AppRoutes.submissionQueuePattern,
    title: "答案キュー",
    subtitle: "取り込んだ答案の確認状況",
  },
  {
    pattern: AppRoutes.submissionConfirmPattern,
    title: "答案の確定",
    subtitle: "読み取った内容を確認して確定します",
  },
  {
    pattern: AppRoutes.pdfReviewPattern,
    title: "添削レビュー",
    subtitle: "答案を採点し、承認します",
  },
];

export function pageTitleFor(pathname: string): string | null {
  for (const { pattern, title } of PAGE_HEADERS) {
    if (matchRoutePattern(pattern, pathname) !== null) {
      return title;
    }
  }
  return null;
}

export function pageSubtitleFor(pathname: string): string | null {
  for (const { pattern, subtitle } of PAGE_HEADERS) {
    if (matchRoutePattern(pattern, pathname) !== null) {
      return subtitle;
    }
  }
  return null;
}
