import { Copy, Minus, ScanText, Square, X } from "lucide-react";
import { useEffect, useState, type JSX } from "react";

/**
 * The custom title bar the frameless windows draw themselves (Issue #428),
 * dressed to read like the OS chrome rather than a pasted-on strip (Issue #446).
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
 * split rather than trusting the CSS string. The app mark and the title are
 * *not* interactive, so they stay on the drag side; they carry the same
 * attribute so a test can pin that (Issue #446).
 *
 * Chrome/VSCode conventions (Issue #446):
 * - the band shares the page's `bg-surface`, so it is continuous with the
 *   content instead of a lighter strip;
 * - the window title is centred (VSCode), not left-aligned; Chrome shows no
 *   title at all, so the bar keeps the app mark on the left to fill that edge;
 * - minimize/maximize hover as a subtle `on-surface` overlay rather than a
 *   solid step on the surface ramp;
 * - the close hover is the fixed Windows red (`--color-window-close-hover`),
 *   not the theme's soft `--color-error`;
 * - when the window loses focus the text and glyphs dim to
 *   `--color-on-surface-muted`, which is how Windows and VSCode tell two open
 *   windows apart. The background does not change.
 */

export const WINDOW_TITLE_BAR_TEST_ID = "window-title-bar";
export const WINDOW_MINIMIZE_TEST_ID = "window-minimize";
export const WINDOW_MAXIMIZE_TEST_ID = "window-maximize";
export const WINDOW_CLOSE_TEST_ID = "window-close";
export const WINDOW_TITLE_BAR_ICON_TEST_ID = "window-title-bar-icon";
export const WINDOW_TITLE_BAR_TITLE_TEST_ID = "window-title-bar-title";

/**
 * Height of the band, shared with the layout that has to leave room for it.
 * 2rem (32px) is the Windows 11 caption height at 100% scale; the root column
 * in `main.tsx` reserves exactly this much and hands the rest to `AppShell`.
 */
export const WINDOW_TITLE_BAR_HEIGHT = "2rem";

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
  /**
   * The glyph colour is inherited from the band (`text-on-surface-variant` or,
   * when the window is not focused, `text-on-surface-muted`), so the whole bar
   * dims together. Only the close button overrides it, on hover, with the
   * fixed Windows red — that is the OS behaviour whether or not the window is
   * focused. `on-surface` at 10% is the "subtle overlay" Windows uses for the
   * other two: a translucent step over any background, not a solid fill of a
   * different surface token.
   */
  const hoverClasses = danger
    ? "hover:bg-window-close-hover hover:text-on-window-close-hover"
    : "hover:bg-on-surface/10";
  return (
    <button
      type="button"
      data-testid={testId}
      aria-label={label}
      title={label}
      aria-pressed={pressed}
      onClick={onClick}
      className={`inline-flex w-11 items-center justify-center transition-colors focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-primary ${hoverClasses}`}
    >
      {children}
    </button>
  );
}

/**
 * The "restore" glyph. lucide's `Copy` name is misleading here, but its
 * drawing is exactly Windows' two-overlapping-squares restore mark — the
 * Issue's own description of the glyph — so the shape is reused under an
 * intent-revealing alias instead of inventing a new SVG (Issue #446).
 */
function WindowRestoreIcon(): JSX.Element {
  return <Copy aria-hidden className="size-4" />;
}

export function WindowTitleBar({
  title = "Auto-Scoring",
}: {
  readonly title?: string;
}): JSX.Element {
  const [maximized, setMaximized] = useState(false);
  const [focused, setFocused] = useState(true);

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

  useEffect(() => {
    const bridge = window.autoScoring;
    if (bridge === undefined) {
      return undefined;
    }
    let active = true;
    if (typeof bridge.isWindowFocused === "function") {
      void bridge.isWindowFocused().then((value) => {
        if (active) {
          setFocused(value);
        }
      });
    }
    const unsubscribe =
      typeof bridge.onWindowFocusChange === "function"
        ? bridge.onWindowFocusChange((value) => {
            if (active) {
              setFocused(value);
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
      data-window-focus={focused ? "focused" : "unfocused"}
      onDoubleClick={toggleMaximize}
      className={`relative flex h-8 shrink-0 select-none items-center bg-surface [-webkit-app-region:drag] ${
        focused ? "text-on-surface-variant" : "text-on-surface-muted"
      }`}
    >
      {/* App mark (Issue #446 item 3). The OS icon used to be the only mark on
          a frameless window; without it the left half of the band read empty.
          It is decorative, so it is `aria-hidden` and stays draggable. */}
      <div
        data-testid={WINDOW_TITLE_BAR_ICON_TEST_ID}
        data-window-drag-region="drag"
        className="flex h-full w-11 shrink-0 items-center justify-center"
      >
        <ScanText
          aria-hidden
          className={`size-4 ${focused ? "text-primary-text" : "text-on-surface-muted"}`}
        />
      </div>
      {/* Centred window title (VSCode). Absolute so it sits at the window's
          centre rather than at the centre of the space the (wider) controls
          leave behind. `inset-x-33` is three `w-11` controls (132px) on each
          side, so the title can never slide under them; `pointer-events-none`
          lets the drag band keep the double-click-to-maximize gesture. */}
      <div
        data-testid={WINDOW_TITLE_BAR_TITLE_TEST_ID}
        data-window-drag-region="drag"
        className="pointer-events-none absolute inset-x-33 inset-y-0 flex items-center justify-center"
      >
        <span className="truncate text-ui-label">{title}</span>
      </div>
      {/* Buttons must not be part of the drag region: `-webkit-app-region`
          inherits, so this container turns it back off. `stopPropagation`
          keeps a fast double-click on a button from also reaching the band's
          maximize toggle. */}
      <div
        data-testid="window-title-bar-controls"
        data-window-drag-region="no-drag"
        className="ml-auto flex h-full shrink-0 items-stretch [-webkit-app-region:no-drag]"
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
            <WindowRestoreIcon />
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
