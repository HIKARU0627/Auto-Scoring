import { AppRoutes } from "../core/app-routes.js";
import { matchRoutePattern } from "./router.js";

/**
 * One line of context under each page heading (Issue #335).
 *
 * The heading itself is supplied by the page (it is often dynamic, e.g. the
 * test name), so only the subtitle is derived from the location. Keeping it
 * here means a new screen gets the shell's heading treatment without the
 * feature file having to know the shell exists.
 */
const PAGE_SUBTITLES: readonly {
  readonly pattern: string;
  readonly subtitle: string;
}[] = [
  { pattern: AppRoutes.home, subtitle: "今日もよい添削を" },
  {
    pattern: AppRoutes.intake,
    subtitle: "答案と採点資料を取り込んで、テストを準備します",
  },
  {
    pattern: AppRoutes.testList,
    subtitle: "登録したテストと答案の進み具合",
  },
  { pattern: AppRoutes.settings, subtitle: "アプリの設定と資格情報" },
  {
    pattern: AppRoutes.testSettingsPattern,
    subtitle: "回答欄と設問の依存関係を確認・修正します",
  },
  {
    pattern: AppRoutes.submissionQueuePattern,
    subtitle: "取り込んだ答案の確認状況",
  },
  {
    pattern: AppRoutes.submissionConfirmPattern,
    subtitle: "読み取った内容を確認して確定します",
  },
  {
    pattern: AppRoutes.pdfReviewPattern,
    subtitle: "答案を採点し、承認します",
  },
];

export function pageSubtitleFor(pathname: string): string | null {
  for (const { pattern, subtitle } of PAGE_SUBTITLES) {
    if (matchRoutePattern(pattern, pathname) !== null) {
      return subtitle;
    }
  }
  return null;
}
