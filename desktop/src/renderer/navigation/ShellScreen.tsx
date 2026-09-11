import type { JSX, ReactNode } from "react";

import { BackOrHomeButton } from "./BackOrHomeButton.js";
import { pageSubtitleFor } from "./page-header.js";
import { useRouter } from "./router.js";

/**
 * Page chrome for a covered route: the escape control, a page heading, its
 * one-line subtitle, and the content region (Issue #335).
 *
 * The heading stays a prop because screens override it with live data (a test
 * or answer name); the subtitle is derived from the location. The content
 * region is deliberately a plain, width-fluid container so a screen can lay
 * out a card grid or a split pane inside it.
 */
export function ShellScreen({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string | undefined;
  children?: ReactNode;
}): JSX.Element {
  const { pathname } = useRouter();
  const resolvedSubtitle = subtitle ?? pageSubtitleFor(pathname);

  return (
    <div className="flex min-h-full min-w-0 flex-col text-on-surface">
      <header className="flex items-start gap-md px-xl pt-lg pb-md">
        <BackOrHomeButton />
        <div className="min-w-0 flex-1">
          <h1
            data-testid="page-title"
            className="text-[length:var(--font-size-headline-medium)] font-medium leading-ui text-on-surface"
          >
            {title}
          </h1>
          {resolvedSubtitle === null ? null : (
            <p className="mt-xs text-body-medium text-on-surface-variant">
              {resolvedSubtitle}
            </p>
          )}
        </div>
      </header>
      <main className="min-w-0 flex-1 px-xl pb-xl">{children}</main>
    </div>
  );
}
