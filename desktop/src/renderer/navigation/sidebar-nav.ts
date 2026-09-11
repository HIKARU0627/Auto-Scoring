import { AppRoutes } from "../core/app-routes.js";

/**
 * The four top-level destinations the persistent sidebar offers (Issue #335,
 * parent #333). Data lives apart from the component so the regression test can
 * pin the list without rendering, and so a future screen can link to the same
 * destinations without importing React.
 */
export interface SidebarNavItem {
  readonly route: string;
  readonly label: string;
  /** Stable hook for the sidebar regression test. */
  readonly testId: string;
}

export const SIDEBAR_NAV_ITEMS: readonly SidebarNavItem[] = [
  { route: AppRoutes.home, label: "ホーム", testId: "sidebar-nav-home" },
  {
    route: AppRoutes.intake,
    label: "資料の取込",
    testId: "sidebar-nav-intake",
  },
  {
    route: AppRoutes.testList,
    label: "テスト一覧",
    testId: "sidebar-nav-tests",
  },
  { route: AppRoutes.settings, label: "設定", testId: "sidebar-nav-settings" },
];

/**
 * Whether a destination should be shown as the current location.
 *
 * Everything under `/tests/` (settings, queues, review) belongs to the test
 * list destination, so drilling into one test keeps "テスト一覧" lit rather
 * than leaving the sidebar with no current location.
 */
export function isSidebarItemActive(pathname: string, route: string): boolean {
  if (route === AppRoutes.home) {
    return pathname === AppRoutes.home;
  }
  if (route === AppRoutes.testList) {
    return (
      pathname === AppRoutes.testList ||
      pathname.startsWith(`${AppRoutes.testList}/`)
    );
  }
  return pathname === route;
}
