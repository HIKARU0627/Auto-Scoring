import { Copy, Minus, Square, X } from "lucide-react";
import { useEffect, useState, type JSX } from "react";

/**
 * The custom title bar the frameless windows draw themselves (Issue #428).
 *
 * `main.ts` creates both windows with `frame: false`, so the OS caption is
 * gone. This component puts it back in the page: a draggable band plus
 * minimize / maximize-restore / close buttons. It talks to the main process
 * only through `window.autoScoring` (the preload bridge); the main process
 * resolves the target window from the IPC sender, so this component never
 * names a window.
 *
 * `-webkit-app-region: drag` is inherited by every descendant, including the
 * buttons, which would make the buttons undraggable as buttons. The controls
 * container therefore sets `no-drag` back. `data-window-drag-region` marks
 * which side of that split an element is on, so the e2e test can assert the
 * split rather than trusting the CSS string.
 */

export const WINDOW_TITLE_BAR_TEST_ID = "window-title-bar";
export const WINDOW_MINIMIZE_TEST_ID = "window-minimize";
export const WINDOW_MAXIMIZE_TEST_ID = "window-maximize";
export const WINDOW_CLOSE_TEST_ID = "window-close";

/**
 * Height of the band, shared with the layout that has to leave room for it.
 * 2.25rem (36px) is the Windows caption height at 100% scale.
 */
export const WINDOW_TITLE_BAR_HEIGHT = "2.25rem";

function WindowControlButton({
  testId,
  label,
  pressed,
  danger = false,
  onClick,
  children,
}: {
  readonly testId: string;
  readonly label: string;
  readonly pressed?: boolean | undefined;
  readonly danger?: boolean | undefined;
  readonly onClick: () => void;
  readonly children: JSX.Element;
}): JSX.Element {
  const dangerClasses = danger
    ? "hover:bg-error hover:text-on-error"
    : "hover:bg-surface-container-high hover:text-on-surface";
  return (
    <button
      type="button"
      data-testid={testId}
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      onClick={onClick}
      className={`inline-flex w-11 items-center justify-center text-on-surface-variant transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary ${dangerClasses}`}
    >
      {children}
    </button>
  );
}

export function WindowTitleBar({
  title = "Auto-Scoring",
}: {
  readonly title?: string;
}): JSX.Element {
  const [maximized, setMaximized] = useState(false);

  useEffect(() => {
    const bridge = window.autoScoring;
    if (bridge === undefined) {
      return undefined;
    }
    let active = true;
    if (typeof bridge.isWindowMaximized === "function") {
      void bridge.isWindowMaximized().then((value) => {
        if (active) {
          setMaximized(value);
        }
      });
    }
    const unsubscribe =
      typeof bridge.onWindowMaximizedChange === "function"
        ? bridge.onWindowMaximizedChange((value) => {
            if (active) {
              setMaximized(value);
            }
          })
        : () => {};
    return () => {
      active = false;
      unsubscribe();
    };
  }, []);

  const toggleMaximize = (): void => {
    void window.autoScoring?.toggleMaximizeWindow?.();
  };

  return (
    <header
      data-testid={WINDOW_TITLE_BAR_TEST_ID}
      data-window-drag-region="drag"
      onDoubleClick={toggleMaximize}
      className="flex h-9 shrink-0 select-none items-center justify-between bg-surface-container-low pl-lg text-on-surface-variant [-webkit-app-region:drag]"
    >
      <span className="truncate text-ui-label">{title}</span>
      {/* Buttons must not be part of the drag region: `-webkit-app-region`
          inherits, so this container turns it back off. `stopPropagation`
          keeps a fast double-click on a button from also reaching the band's
          maximize toggle. */}
      <div
        data-testid="window-title-bar-controls"
        data-window-drag-region="no-drag"
        className="flex h-full shrink-0 items-stretch [-webkit-app-region:no-drag]"
        onDoubleClick={(event) => {
          event.stopPropagation();
        }}
      >
        <WindowControlButton
          testId={WINDOW_MINIMIZE_TEST_ID}
          label="最小化"
          onClick={() => {
            void window.autoScoring?.minimizeWindow?.();
          }}
        >
          <Minus aria-hidden className="size-4" />
        </WindowControlButton>
        <WindowControlButton
          testId={WINDOW_MAXIMIZE_TEST_ID}
          label={maximized ? "元に戻す" : "最大化"}
          pressed={maximized}
          onClick={toggleMaximize}
        >
          {/* Both the glyph and the accessible name change with the state, so
              "which one this button will do" is never carried by colour or by
              one icon alone. */}
          {maximized ? (
            <Copy aria-hidden className="size-4" />
          ) : (
            <Square aria-hidden className="size-4" />
          )}
        </WindowControlButton>
        <WindowControlButton
          testId={WINDOW_CLOSE_TEST_ID}
          label="閉じる"
          danger
          onClick={() => {
            void window.autoScoring?.closeWindow?.();
          }}
        >
          <X aria-hidden className="size-4" />
        </WindowControlButton>
      </div>
    </header>
  );
}
