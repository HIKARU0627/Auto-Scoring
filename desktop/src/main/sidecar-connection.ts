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

/**
 * The only host the sidecar is allowed to answer on (INV-203).
 *
 * A literal, not a name: `localhost` resolves through DNS, and a name that
 * resolves somewhere else would send the bearer token off the loopback.
 */
const LOOPBACK_HOST = "127.0.0.1";

/**
 * Raised when a request would leave loopback. The message is a fixed string on
 * purpose: it must never echo the host, the port, or the bearer token into a
 * log or an error banner (INV-203).
 */
export class UnsafeSidecarConnectionError extends Error {
  constructor() {
    super("refusing a non-loopback sidecar connection");
    this.name = "UnsafeSidecarConnectionError";
  }
}

/** Whether `host` is the loopback literal the sidecar binds (INV-203). */
export function isLoopbackHost(host: string): boolean {
  return host === LOOPBACK_HOST;
}

/**
 * Rejects a connection whose host is not loopback. The handshake file is
 * attacker-controlled input once anything can write to it, so the host is
 * re-validated at the request boundary rather than trusted from the handshake.
 */
export function assertLoopbackConnection(
  connection: InternalSidecarConnection,
): void {
  if (!isLoopbackHost(connection.host)) {
    throw new UnsafeSidecarConnectionError();
  }
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
