import type {
  SidecarFetchRequest,
  SidecarFetchResponse,
} from "../../shared/sidecar-fetch.js";

type MutableSidecarFetchRequest = {
  method: string;
  urlPath: string;
  headers?: Readonly<Record<string, string>>;
  bodyBase64?: string;
};

function uint8ArrayToBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) {
    binary += String.fromCharCode(byte);
  }
  return btoa(binary);
}

function base64ToUint8Array(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let index = 0; index < binary.length; index += 1) {
    bytes[index] = binary.charCodeAt(index);
  }
  return bytes;
}

function collectHeaders(request: Request): Record<string, string> {
  const headers: Record<string, string> = {};
  request.headers.forEach((value, key) => {
    if (key.toLowerCase() !== "authorization") {
      headers[key] = value;
    }
  });
  return headers;
}

async function invokeSidecarFetch(
  request: SidecarFetchRequest,
): Promise<SidecarFetchResponse> {
  const bridge = window.autoScoring;
  if (bridge === undefined) {
    throw new TypeError("autoScoring bridge is not available");
  }
  return await bridge.sidecarFetch(request);
}

/**
 * Fetch implementation that forwards HTTP to the main process (Issue #264).
 * The renderer's CSP blocks loopback `connect-src`, so all sidecar traffic
 * crosses IPC instead.
 */
export function createIpcFetch(): typeof fetch {
  return async (input, init) => {
    const request = new Request(input, init);
    const url = new URL(request.url);

    let bodyBase64: string | undefined;
    if (request.method !== "GET" && request.method !== "HEAD") {
      const buffer = await request.arrayBuffer();
      if (buffer.byteLength > 0) {
        bodyBase64 = uint8ArrayToBase64(new Uint8Array(buffer));
      }
    }

    const ipcRequest: MutableSidecarFetchRequest = {
      method: request.method,
      urlPath: `${url.pathname}${url.search}`,
      headers: collectHeaders(request),
    };
    if (bodyBase64 !== undefined) {
      ipcRequest.bodyBase64 = bodyBase64;
    }

    const ipcResponse = await invokeSidecarFetch(ipcRequest);

    const bytes = base64ToUint8Array(ipcResponse.bodyBase64);
    const body = bytes.buffer.slice(
      bytes.byteOffset,
      bytes.byteOffset + bytes.byteLength,
    ) as ArrayBuffer;
    return new Response(body, {
      status: ipcResponse.status,
      statusText: ipcResponse.statusText,
      headers: ipcResponse.headers,
    });
  };
}
