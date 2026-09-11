import type {
  SidecarFetchRequest,
  SidecarFetchResponse,
} from "../shared/sidecar-fetch.js";
import type { InternalSidecarConnection } from "./sidecar-connection.js";

function headersToRecord(headers: Headers): Readonly<Record<string, string>> {
  const record: Record<string, string> = {};
  headers.forEach((value, key) => {
    record[key] = value;
  });
  return record;
}

/**
 * Performs an HTTP request against the sidecar from the main process.
 * Authorization is attached here so the renderer never sees the token.
 */
export async function sidecarFetch(
  connection: InternalSidecarConnection,
  request: SidecarFetchRequest,
): Promise<SidecarFetchResponse> {
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

  const response = await fetch(url, fetchInit);

  const responseBuffer = Buffer.from(await response.arrayBuffer());
  return {
    status: response.status,
    statusText: response.statusText,
    headers: headersToRecord(response.headers),
    bodyBase64: responseBuffer.toString("base64"),
  };
}
