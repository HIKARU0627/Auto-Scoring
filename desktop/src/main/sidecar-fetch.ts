import type {
  SidecarFetchRequest,
  SidecarFetchResponse,
} from "../shared/sidecar-fetch.js";
import {
  assertLoopbackConnection,
  type InternalSidecarConnection,
} from "./sidecar-connection.js";

function headersToRecord(headers: Headers): Readonly<Record<string, string>> {
  const record: Record<string, string> = {};
  headers.forEach((value, key) => {
    record[key] = value;
  });
  return record;
}

/**
 * Raised when the request fails before the sidecar answers. The message is a
 * fixed string on purpose: a transport failure's own text can name the URL, the
 * port, or the token, and none of those may reach a log or an error banner
 * (INV-204).
 */
export class SidecarTransportError extends Error {
  constructor() {
    super("sidecar request failed");
    this.name = "SidecarTransportError";
  }
}

/**
 * Performs an HTTP request against the sidecar from the main process.
 * Authorization is attached here so the renderer never sees the token.
 *
 * The connection is checked against loopback first (INV-203), and any
 * transport failure is collapsed into a sanitized {@link SidecarTransportError}
 * (INV-204) rather than rethrown with its host, port, or token.
 */
export async function sidecarFetch(
  connection: InternalSidecarConnection,
  request: SidecarFetchRequest,
): Promise<SidecarFetchResponse> {
  assertLoopbackConnection(connection);

  const url = `http://${connection.host}:${connection.port}${request.urlPath}`;
  const headers = new Headers(request.headers ?? {});
  headers.set("Authorization", `Bearer ${connection.token}`);

  const fetchInit: RequestInit = {
    method: request.method,
    headers,
  };
  if (request.bodyBase64 !== undefined && request.bodyBase64.length > 0) {
    fetchInit.body = Buffer.from(request.bodyBase64, "base64");
  }

  let response: Response;
  let responseBuffer: Buffer;
  try {
    response = await fetch(url, fetchInit);
    responseBuffer = Buffer.from(await response.arrayBuffer());
  } catch {
    // The cause is deliberately dropped: it can carry the host and port.
    throw new SidecarTransportError();
  }

  return {
    status: response.status,
    statusText: response.statusText,
    headers: headersToRecord(response.headers),
    bodyBase64: responseBuffer.toString("base64"),
  };
}
