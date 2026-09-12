import type { JSX } from "react";

import { AppRoutes } from "../core/app-routes.js";
import { HomePage } from "../features/home/HomePage.js";
import { IntakePage } from "../features/intake/IntakePage.js";
import { PdfReviewPage } from "../features/pdf-review/PdfReviewPage.js";
import { SubmissionQueuePage } from "../features/review-queue/SubmissionQueuePage.js";
import { SubmissionConfirmPage } from "../features/submission-confirm/SubmissionConfirmPage.js";
import { SettingsPage } from "../features/settings/SettingsPage.js";
import { TestListPage } from "../features/test-list/TestListPage.js";
import { TestSettingsPage } from "../features/test-settings/TestSettingsPage.js";
import { ShellScreen } from "./ShellScreen.js";
import { matchRoutePattern } from "./router.js";
import { useRouter } from "./router.js";

export interface RouteDefinition {
  readonly pattern: string;
  readonly render: () => JSX.Element;
}

export const ROUTE_TABLE: readonly RouteDefinition[] = [
  { pattern: AppRoutes.home, render: () => <HomePage /> },
  {
    pattern: AppRoutes.starting,
    render: () => <div data-testid="route-starting" />,
  },
  {
    pattern: AppRoutes.intake,
    render: () => <IntakePage />,
  },
  {
    pattern: AppRoutes.settings,
    render: () => <SettingsPage />,
  },
  {
    pattern: AppRoutes.testList,
    render: () => <TestListPage />,
  },
  {
    pattern: AppRoutes.testSettingsPattern,
    render: () => <TestSettingsPage />,
  },
  {
    pattern: AppRoutes.submissionQueuePattern,
    render: () => <SubmissionQueuePage />,
  },
  {
    pattern: AppRoutes.submissionConfirmPattern,
    render: () => <SubmissionConfirmPage />,
  },
  {
    pattern: AppRoutes.pdfReviewPattern,
    render: () => <PdfReviewPage />,
  },
];

export function RouteOutlet(): JSX.Element {
  const { location } = useRouter();
  for (const route of ROUTE_TABLE) {
    if (matchRoutePattern(route.pattern, location) !== null) {
      return route.render();
    }
  }
  return (
    <ShellScreen title="画面が見つかりません">
      <p className="text-body-medium text-on-surface-variant">{location}</p>
    </ShellScreen>
  );
}
