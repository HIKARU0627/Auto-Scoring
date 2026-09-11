import type { JSX, ReactNode } from "react";

/**
 * The small set of shapes the refreshed screens share (Issue #346, parent #333).
 *
 * The mock (`UI_Home.png`) separates information with rounded surfaces and a
 * brightness difference rather than borders, marks state with round pills, and
 * shows progress as a bar with a percentage. These primitives keep that
 * language in one place so the intake and test-settings screens do not each
 * invent their own card, pill, and stepper. Every visual value is a token
 * utility; the design-token lint test forbids literals here (INV-080).
 */

export type StatusTone =
  "success" | "attention" | "info" | "primary" | "neutral";

const STATUS_TONE_CLASS: Record<StatusTone, string> = {
  success: "bg-success-container text-on-success-container",
  attention: "bg-attention-container text-on-attention-container",
  info: "bg-info-container text-on-info-container",
  primary: "bg-primary-container text-on-primary-container",
  neutral: "bg-surface-container-high text-on-surface-variant",
};

/** A round state label: 完了 / 要確認 / 処理中 / 未確認. */
export function StatusPill({
  tone,
  testId,
  children,
}: {
  tone: StatusTone;
  testId?: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <span
      data-testid={testId}
      className={`inline-flex items-center whitespace-nowrap rounded-full px-sm py-xs text-ui-label ${STATUS_TONE_CLASS[tone]}`}
    >
      {children}
    </span>
  );
}

/** A rounded surface card. No border: the surface difference does the work. */
export function Card({
  testId,
  className,
  children,
}: {
  testId?: string;
  className?: string;
  children: ReactNode;
}): JSX.Element {
  return (
    <section
      data-testid={testId}
      className={["rounded-xl bg-surface-container p-lg", className ?? ""]
        .join(" ")
        .trim()}
    >
      {children}
    </section>
  );
}

/** Card title, optional one-line description, and a trailing state control. */
export function CardHeading({
  title,
  titleTestId,
  description,
  aside,
}: {
  title: string;
  titleTestId?: string;
  description?: string;
  aside?: ReactNode;
}): JSX.Element {
  return (
    <div className="flex flex-wrap items-start justify-between gap-md">
      <div className="min-w-0 flex-1">
        <h2
          data-testid={titleTestId}
          className="text-recognized font-medium leading-ui text-on-surface"
        >
          {title}
        </h2>
        {description === undefined ? null : (
          <p className="mt-xs text-body-medium text-on-surface-variant">
            {description}
          </p>
        )}
      </div>
      {aside === undefined ? null : <div className="shrink-0">{aside}</div>}
    </div>
  );
}

export interface ProgressStep {
  readonly id: string;
  readonly label: string;
  readonly complete: boolean;
}

/**
 * A one-glance progress trail across a screen's stages.
 *
 * `currentId` marks the stage the reviewer is on. A completed stage is never
 * the current one, so the screen only has to say what is done and where it is
 * now -- the remaining stages are derived, not tracked.
 */
export function StepProgress({
  testId,
  steps,
  currentId,
}: {
  testId: string;
  steps: readonly ProgressStep[];
  currentId: string | null;
}): JSX.Element {
  return (
    <ol
      data-testid={testId}
      className="flex flex-wrap items-center gap-sm text-ui-label"
    >
      {steps.map((step, index) => {
        const current = step.id === currentId && !step.complete;
        const state = step.complete ? "done" : current ? "current" : "upcoming";
        const shape = step.complete
          ? "bg-success-container text-on-success-container"
          : current
            ? "bg-primary text-on-primary"
            : "bg-surface-container-high text-on-surface-variant";
        return (
          <li
            key={step.id}
            data-testid={`${testId}-${step.id}`}
            data-state={state}
            aria-current={current ? "step" : undefined}
            className="flex items-center gap-sm"
          >
            <span
              className={`flex items-center gap-sm rounded-full px-md py-xs ${shape}`}
            >
              <span aria-hidden className="tabular-nums">
                {step.complete ? "✓" : index + 1}
              </span>
              <span>{step.label}</span>
              <span className="sr-only">
                {step.complete ? "（完了）" : current ? "（現在）" : ""}
              </span>
            </span>
            {index < steps.length - 1 ? (
              <span aria-hidden className="text-on-surface-variant">
                ›
              </span>
            ) : null}
          </li>
        );
      })}
    </ol>
  );
}

/**
 * A labelled progress bar with a percentage.
 *
 * `max` must be a real, known total. Callers never render this with an unknown
 * or zero total: a bar stuck at 0% would read as "nothing done" when the truth
 * is "not measured yet" (Issue #346 acceptance, `0` vs 取得できていない).
 */
export function ProgressMeter({
  testId,
  label,
  value,
  max,
  tone = "primary",
}: {
  testId?: string;
  label: string;
  value: number;
  max: number;
  tone?: "primary" | "success";
}): JSX.Element {
  const percent = Math.max(0, Math.min(100, Math.round((value / max) * 100)));
  return (
    <div data-testid={testId}>
      <div className="flex items-baseline justify-between gap-sm">
        <span className="text-body-medium text-on-surface-variant">
          {label}
        </span>
        <span className="tabular-nums text-body-medium text-on-surface">
          {percent}%
        </span>
      </div>
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={value}
        className="mt-xs h-2 overflow-hidden rounded-full bg-progress-track"
      >
        <div
          className={`h-full rounded-full ${
            tone === "success" ? "bg-success" : "bg-primary"
          }`}
          style={{ width: `${percent}%` }}
        />
      </div>
    </div>
  );
}

/**
 * What is running right now, and roughly how long it takes.
 *
 * A fixed "処理中…" is not enough on the two screens where an AI call runs for
 * tens of seconds: the reviewer has to know which step is running and what the
 * wait is for.
 */
export function BusyNotice({
  testId,
  title,
  detail,
}: {
  testId: string;
  title: string;
  detail: string;
}): JSX.Element {
  return (
    <div
      data-testid={testId}
      role="status"
      aria-live="polite"
      className="flex items-start gap-md rounded-xl bg-surface-container-high p-lg"
    >
      <Spinner />
      <div className="min-w-0 flex-1">
        <p className="text-recognized font-medium leading-ui text-on-surface">
          {title}
        </p>
        <p className="mt-xs text-body-medium text-on-surface-variant">
          {detail}
        </p>
      </div>
    </div>
  );
}

export function Spinner(): JSX.Element {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      className="mt-xs h-5 w-5 shrink-0 animate-spin text-primary"
    >
      <circle
        cx="12"
        cy="12"
        r="9"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        opacity="0.25"
      />
      <path
        d="M21 12a9 9 0 0 0-9-9"
        fill="none"
        stroke="currentColor"
        strokeWidth="3"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** A placeholder block that keeps the ready layout's height while loading. */
export function SkeletonBlock({
  className,
}: {
  className?: string;
}): JSX.Element {
  return (
    <div
      aria-hidden
      className={`animate-pulse rounded-lg bg-surface-container-high ${className ?? ""}`}
    />
  );
}

/** Card-shaped skeleton group so a loading screen does not jump on arrival. */
export function ScreenSkeleton({
  testId,
  cardCount = 3,
}: {
  testId: string;
  cardCount?: number;
}): JSX.Element {
  return (
    <div data-testid={testId} className="flex flex-col gap-xl">
      <SkeletonBlock className="h-12 w-full" />
      {Array.from({ length: cardCount }, (_, index) => (
        <div
          key={`skeleton-${index}`}
          className="rounded-xl bg-surface-container p-lg"
        >
          <SkeletonBlock className="h-6 w-48" />
          <SkeletonBlock className="mt-md h-4 w-full" />
          <SkeletonBlock className="mt-sm h-4 w-3/4" />
          <SkeletonBlock className="mt-lg h-10 w-40" />
        </div>
      ))}
    </div>
  );
}

/** A titled section of related cards. */
export function SectionHeading({
  title,
  count,
}: {
  title: string;
  count?: number;
}): JSX.Element {
  return (
    <div className="flex items-baseline justify-between gap-md">
      <h2 className="text-recognized font-medium leading-ui text-on-surface">
        {title}
      </h2>
      {count === undefined ? null : (
        <span className="tabular-nums text-body-medium text-on-surface-variant">
          {count}件
        </span>
      )}
    </div>
  );
}

/** An error surface that names what failed and offers the next action. */
export function ErrorNotice({
  testId,
  children,
  action,
}: {
  testId: string;
  children: ReactNode;
  action?: ReactNode;
}): JSX.Element {
  return (
    <div
      data-testid={testId}
      role="alert"
      className="flex items-start gap-md rounded-xl bg-error-container p-lg text-on-error-container"
    >
      <svg aria-hidden viewBox="0 0 24 24" className="mt-xs h-5 w-5 shrink-0">
        <circle
          cx="12"
          cy="12"
          r="9"
          fill="none"
          stroke="currentColor"
          strokeWidth="2"
        />
        <path
          d="M12 7.5v5.5"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
        />
        <circle cx="12" cy="16.5" r="1" fill="currentColor" />
      </svg>
      <div className="min-w-0 flex-1 text-body-medium">{children}</div>
      {action === undefined ? null : <div className="shrink-0">{action}</div>}
    </div>
  );
}

/** Button classes shared by both screens: four states, visible focus. */
export function primaryButtonClass(extra?: string): string {
  return [
    "inline-flex items-center justify-center gap-sm rounded-md bg-primary px-md py-sm text-ui-label text-on-primary",
    "transition-colors hover:bg-primary-container hover:text-on-primary-container",
    "active:bg-primary-container active:text-on-primary-container",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
    "disabled:cursor-not-allowed disabled:bg-disabled-button-container disabled:text-disabled-button-label",
    extra ?? "",
  ]
    .join(" ")
    .trim();
}

export function secondaryButtonClass(extra?: string): string {
  return [
    "inline-flex items-center justify-center gap-sm rounded-md bg-surface-container-high px-md py-sm text-ui-label text-on-surface",
    "transition-colors hover:bg-surface-container-highest active:bg-surface-container-highest",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
    "disabled:cursor-not-allowed disabled:bg-disabled-button-container disabled:text-disabled-button-label",
    extra ?? "",
  ]
    .join(" ")
    .trim();
}

export function outlineButtonClass(extra?: string): string {
  return [
    "inline-flex items-center justify-center gap-sm rounded-md border border-outline bg-transparent px-md py-sm text-ui-label text-on-surface",
    "transition-colors hover:bg-surface-container-high active:bg-surface-container-highest",
    "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-primary",
    "disabled:cursor-not-allowed disabled:border-disabled-button-outline disabled:text-disabled-button-label",
    extra ?? "",
  ]
    .join(" ")
    .trim();
}
