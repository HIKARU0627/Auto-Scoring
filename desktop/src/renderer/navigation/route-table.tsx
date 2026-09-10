import type { JSX } from "react";

import { AppRoutes } from "../core/app-routes.js";
import { HomePage } from "../features/home/HomePage.js";
import { IntakePage } from "../features/intake/IntakePage.js";
import { TestSettingsPage } from "../features/test-settings/TestSettingsPage.js";
import { ShellScreen } from "./ShellScreen.js";
import { matchRoutePattern } from "./router.js";
import { useRouter } from "./router.js";

export interface RouteDefinition {
  readonly pattern: string;
  readonly render: () => JSX.Element;
}

function PlaceholderScreen({ title }: { title: string }): JSX.Element {
  const { params } = useRouter();
  const details = [
    params.testId !== undefined ? `testId=${params.testId}` : null,
    params.submissionId !== undefined
      ? `submissionId=${params.submissionId}`
      : null,
    params.questionId !== undefined ? `question=${params.questionId}` : null,
  ]
    .filter((line) => line !== null)
    .join(", ");

  return (
    <ShellScreen title={title}>
      {details.length > 0 ? (
        <p className="text-body-medium text-on-surface-variant">{details}</p>
      ) : null}
    </ShellScreen>
  );
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
    render: () => <PlaceholderScreen title="設定" />,
  },
  {
    pattern: AppRoutes.testList,
    render: () => <PlaceholderScreen title="テスト一覧" />,
  },
  {
    pattern: AppRoutes.testSettingsPattern,
    render: () => <TestSettingsPage />,
  },
  {
    pattern: AppRoutes.submissionQueuePattern,
    render: () => <PlaceholderScreen title="答案キュー" />,
  },
  {
    pattern: AppRoutes.submissionConfirmPattern,
    render: () => <PlaceholderScreen title="答案確定" />,
  },
  {
    pattern: AppRoutes.pdfReviewPattern,
    render: () => <PlaceholderScreen title="添削レビュー" />,
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
