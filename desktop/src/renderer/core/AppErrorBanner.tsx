import { useEffect, useState, type JSX } from "react";

/**
 * The recoverable-failure banner every screen shows in the same place and the
 * same shape (INV-096, Issue #272): what failed, in Japanese, and the one
 * button that retries it.
 *
 * The retry button is *shown disabled* rather than removed while a retry is
 * already running (`onRetry === null`), so the banner does not change size
 * under the reviewer's pointer. `retryable={false}` is for the failures that
 * have no single thing to re-run.
 *
 * It fades and lifts in once on mount and then stops. The motion budget is
 * deliberately one-shot: a banner that never settled would keep the reviewer's
 * eye (and `pumpAndSettle`) busy forever.
 */

/** Matches `--motion-duration-emphasis` in `styles/design-tokens.css`. */
const ENTER_MS = 250;

export interface AppErrorBannerProps {
  /** Identifies the banner for tests that assert on *this* screen. */
  readonly testId?: string;
  readonly message: string;
  /** Identifies the message text when a screen has several banners. */
  readonly messageTestId?: string;
  /** `null` while a retry is already running: the button is then disabled. */
  readonly onRetry?: (() => void) | null;
  /** `false` where the failure has no single thing to re-run. */
  readonly retryable?: boolean;
  readonly retryLabel?: string;
}

export function AppErrorBanner({
  testId = "app-error-banner",
  message,
  messageTestId,
  onRetry,
  retryable = true,
  retryLabel = "再試行",
}: AppErrorBannerProps): JSX.Element {
  const [entering, setEntering] = useState(true);

  useEffect(() => {
    const timer = window.setTimeout(() => {
      setEntering(false);
    }, ENTER_MS);
    return () => {
      window.clearTimeout(timer);
    };
  }, []);

  return (
    <div
      role="alert"
      data-testid={testId}
      data-enter={entering ? "running" : "settled"}
      className="flex items-start gap-sm rounded-md border border-error bg-error-container p-lg text-on-error-container"
      style={{
        opacity: entering ? 0 : 1,
        transform: entering ? "translateY(var(--spacing-sm))" : "none",
        transition: `opacity ${ENTER_MS}ms var(--motion-easing-enter), transform ${ENTER_MS}ms var(--motion-easing-enter)`,
      }}
    >
      <span
        aria-hidden
        data-testid={`${testId}-icon`}
        className="material-symbols-outlined shrink-0"
      >
        error_outline
      </span>
      <p
        data-testid={messageTestId}
        className="min-w-0 flex-1 text-body-medium"
      >
        {message}
      </p>
      {retryable ? (
        <button
          type="button"
          data-testid={`${testId}-retry`}
          disabled={onRetry == null}
          onClick={onRetry ?? undefined}
          className="shrink-0 rounded-md border border-outline px-md py-xs text-ui-label disabled:opacity-50"
        >
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}
