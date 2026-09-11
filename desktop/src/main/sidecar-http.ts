import {
  type SidecarHttpRequest,
  type SidecarHttpResponse,
} from "../shared/sidecar-http.js";

/**
 * Performs a sidecar HTTP call from the main process. The renderer cannot use
 * `fetch` against loopback when the page is loaded from `file://`, so JSON API
 * traffic is proxied here while multipart uploads stay on
 * {@link sidecarMultipartUpload}.
 */
export async function sidecarHttpRequest(
  request: SidecarHttpRequest,
): Promise<SidecarHttpResponse> {
  const { connection, method, urlPath, headers, body } = request;
  if (!urlPath.startsWith("/")) {
    throw new Error("sidecar urlPath must start with /");
  }

  const url = `http://${connection.host}:${connection.port}${urlPath}`;
  const forwardedHeaders: Record<string, string> = {};
  if (headers !== undefined) {
    for (const [key, value] of Object.entries(headers)) {
      if (key.toLowerCase() === "authorization") {
        continue;
      }
      forwardedHeaders[key] = value;
    }
  }
  const init: RequestInit = {
    method,
    headers: {
      ...forwardedHeaders,
      Authorization: `Bearer ${connection.token}`,
    },
  };
  if (body !== null && body !== undefined) {
    init.body = body;
  }
  const response = await fetch(url, init);

  const responseHeaders: Record<string, string> = {};
  response.headers.forEach((value, key) => {
    responseHeaders[key] = value;
  });

  const contentType = response.headers.get("content-type") ?? "";
  if (isBinaryContentType(contentType)) {
    const bytes = new Uint8Array(await response.arrayBuffer());
    return {
      status: response.status,
      headers: responseHeaders,
      body: Buffer.from(bytes).toString("base64"),
      encoding: "base64",
    };
  }

  const text = await response.text();
  return {
    status: response.status,
    headers: responseHeaders,
    body: text,
    encoding: "text",
  };
}

function isBinaryContentType(contentType: string): boolean {
  const normalized = contentType.toLowerCase();
  return (
    normalized.startsWith("image/") ||
    normalized.startsWith("application/pdf") ||
    normalized.startsWith("application/octet-stream")
  );
}
