import type { SidecarConnectionInfo } from "./bridge.js";

/** JSON/text sidecar request issued from the renderer through IPC. */
export interface SidecarHttpRequest {
  readonly connection: SidecarConnectionInfo;
  readonly method: string;
  /** Path and query only, e.g. `/test-registrations` or `/tests/{id}/criteria`. */
  readonly urlPath: string;
  readonly headers?: Readonly<Record<string, string>>;
  readonly body?: string | null;
}

/** Sidecar HTTP response serialized back to the renderer. */
export interface SidecarHttpResponse {
  readonly status: number;
  readonly headers: Readonly<Record<string, string>>;
  readonly body: string;
  /** Defaults to `text`. Set to `base64` for image/binary payloads. */
  readonly encoding?: "text" | "base64";
}
