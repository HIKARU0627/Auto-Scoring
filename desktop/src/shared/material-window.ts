/**
 * IPC contract for the separate material window (Issue #415).
 *
 * The owner asked for the imported materials to open in **another window**.
 * A renderer must not open windows of its own (`main.ts` denies
 * `setWindowOpenHandler` on purpose), so the renderer *asks* the main process
 * to open one and the main process owns the single window. These payloads are
 * plain identifiers -- no bytes -- so `src/shared/bridge.ts` stays free of
 * binary payload types (`desktop/test/architecture.test.ts`).
 */

export interface MaterialWindowRequest {
  /** The test whose materials the window should show. */
  readonly testId: string;
  /**
   * A material to select when the window opens. Omitted means "just the list";
   * the window still lets the reviewer pick one.
   */
  readonly materialId?: string;
}

/**
 * What the material window is currently showing.
 *
 * The main process keeps the last value and replays it to a newly created
 * window, so a window that opens after the request still knows what to show.
 */
export interface MaterialWindowSelection {
  readonly testId: string;
  readonly materialId: string | null;
}
