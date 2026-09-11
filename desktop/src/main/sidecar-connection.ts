import type {
  SidecarFailure,
  SidecarConnectionInfo,
  SidecarStatus,
} from "../shared/bridge.js";

/** Loopback connection details including the bearer token (main process only). */
export interface InternalSidecarConnection {
  readonly host: string;
  readonly port: number;
  readonly token: string;
}

export type InternalSidecarStatus =
  | { readonly kind: "starting" }
  | { readonly kind: "ready"; readonly connection: InternalSidecarConnection }
  | {
      readonly kind: "failed";
      readonly failure: SidecarFailure;
      readonly exitCode: number | null;
    }
  | { readonly kind: "stopped" };

export function toPublicSidecarStatus(
  status: InternalSidecarStatus,
): SidecarStatus {
  if (status.kind !== "ready") {
    return status;
  }
  const connection: SidecarConnectionInfo = {
    host: status.connection.host,
    port: status.connection.port,
  };
  return { kind: "ready", connection };
}

export function getReadyConnection(
  status: InternalSidecarStatus,
): InternalSidecarConnection | null {
  return status.kind === "ready" ? status.connection : null;
}
