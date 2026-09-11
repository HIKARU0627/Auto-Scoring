/**
 * IPC contract for HTTP requests the main process performs against the sidecar.
 *
 * Request and response bodies cross the bridge as base64 strings so
 * `src/shared/bridge.ts` stays free of binary payload types.
 */

export interface SidecarFetchRequest {
  readonly method: string;
  /** Path and query only, e.g. `/tests?limit=10`. */
  readonly urlPath: string;
  readonly headers?: Readonly<Record<string, string>>;
  readonly bodyBase64?: string;
}

export interface SidecarFetchResponse {
  readonly status: number;
  readonly statusText: string;
  readonly headers: Readonly<Record<string, string>>;
  readonly bodyBase64: string;
}
