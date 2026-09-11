/**
 * Rendered page image state, shared by the core data loaders
 * (`core/pdf-review-data.ts`) and the answer-area editor UI.
 *
 * It lives in `core` because the data loaders are the ones that build it, and
 * `api` / `core` must not reach into `features` for a type (INV-001 / INV-002).
 */
export interface PageImageState {
  readonly objectUrl: string | null;
  readonly pixelWidth: number | null;
  readonly pixelHeight: number | null;
}
