import type { JSX } from "react";

import { AppRoutes } from "../core/app-routes.js";

/**
 * Solid nav glyphs for the sidebar (Issue #335, polished in Issue #348, sized in
 * Issue #361).
 *
 * The mock's icons are filled silhouettes, not 2px line drawings; a line icon
 * reads much lighter than the mock (`#333` evaluation A, item 5). They stay
 * hand-written rather than pulling in an icon package: the renderer needs four
 * glyphs and `lucide-react` ships stroke paths, not fills. The paths follow the
 * Material 24px grid and are filled with `currentColor`, so the active pill
 * turns them `on-primary` and the rest ride `sidebar-nav-idle`. Inner strokes
 * (the document rules, the gear hub) are knocked out with `fillRule="evenodd"`
 * so they read as the surface behind them, exactly as the mock does.
 *
 * Issue #361: the mock's ~18x24 ink sits ~1.3-1.5x larger than the 20px box the
 * glyphs had, so the viewBox is rendered at 28px.
 */
const ICON_PROPS = {
  width: 28,
  height: 28,
  viewBox: "0 0 24 24",
  fill: "currentColor",
  fillRule: "evenodd",
  xmlns: "http://www.w3.org/2000/svg",
  "aria-hidden": true,
} as const;

export function SidebarNavIcon({
  route,
}: {
  readonly route: string;
}): JSX.Element {
  switch (route) {
    case AppRoutes.home:
      return (
        <svg {...ICON_PROPS}>
          <path d="M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z" />
        </svg>
      );
    case AppRoutes.intake:
      return (
        <svg {...ICON_PROPS}>
          <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z" />
        </svg>
      );
    case AppRoutes.testList:
      return (
        <svg {...ICON_PROPS}>
          <path d="M19 3H5c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h14c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm-5 14H7v-2h7v2zm3-4H7v-2h10v2zm0-4H7V7h10v2z" />
        </svg>
      );
    default:
      return (
        <svg {...ICON_PROPS}>
          <path d="M19.14 12.94c.04-.3.06-.61.06-.94 0-.32-.02-.64-.07-.94l2.03-1.58c.18-.14.23-.41.12-.61l-1.92-3.32c-.12-.22-.37-.29-.59-.22l-2.39.96c-.5-.38-1.03-.7-1.62-.94l-.36-2.54c-.04-.24-.24-.41-.48-.41h-3.84c-.24 0-.43.17-.47.41l-.36 2.54c-.59.24-1.13.57-1.62.94l-2.39-.96c-.22-.08-.47 0-.59.22L2.74 8.87c-.12.21-.08.47.12.61l2.03 1.58c-.05.3-.09.63-.09.94s.02.64.07.94l-2.03 1.58c-.18.14-.23.41-.12.61l1.92 3.32c.12.22.37.29.59.22l2.39-.96c.5.38 1.03.7 1.62.94l.36 2.54c.05.24.24.41.48.41h3.84c.24 0 .44-.17.47-.41l.36-2.54c.59-.24 1.13-.56 1.62-.94l2.39.96c.22.08.47 0 .59-.22l1.92-3.32c.12-.22.07-.47-.12-.61l-2.01-1.58zM12 15.6c-1.98 0-3.6-1.62-3.6-3.6s1.62-3.6 3.6-3.6 3.6 1.62 3.6 3.6-1.62 3.6-3.6 3.6z" />
        </svg>
      );
  }
}
