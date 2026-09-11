/**
 * Typed HTTP client for the Python sidecar.
 *
 * Types come from OpenAPI (`generated/schema.ts`); this file only wires
 * `openapi-fetch` with auth and the loopback base URL. Call sites use the
 * generated path/method names directly — there are no coordinate helpers here.
 * Normalized coordinates are built from the returned image's pixel size only
 * (docs/sidecar-api.md §7); geometry fields are for layout and paging, not
 * for dividing click positions.
 */

import createClient, { type Middleware } from "openapi-fetch";

import type { paths } from "./generated/schema.js";

/** Loopback connection details from the sidecar handshake file. */
export interface SidecarConnection {
  readonly host: string;
  readonly port: number;
  readonly token: string;
}

export type SidecarClient = ReturnType<typeof createSidecarClient>;

function createIpcSidecarFetch(
  connection: SidecarConnection,
): (input: Request) => Promise<Response> {
  const expectedOrigin = `http://${connection.host}:${connection.port}`;

  return async (input: Request) => {
    const url = new URL(input.url);
    if (url.origin !== expectedOrigin) {
      throw new TypeError(
        `Sidecar client requests must target ${expectedOrigin}`,
      );
    }

    const bridge = window.autoScoring;
    const headers: Record<string, string> = {};
    input.headers.forEach((value, key) => {
      headers[key] = value;
    });
    const body =
      input.method === "GET" || input.method === "HEAD"
        ? null
        : await input.text();

    const result = await bridge.sidecarFetch({
      connection,
      method: input.method,
      urlPath: `${url.pathname}${url.search}`,
      headers,
      body,
    });

    const responseBody =
      result.encoding === "base64"
        ? Uint8Array.from(atob(result.body), (character) =>
            character.charCodeAt(0),
          )
        : result.body;

    return new Response(responseBody, {
      status: result.status,
      headers: result.headers,
    });
  };
}

/** Builds the typed fetch client for `paths` from handshake connection info. */
export function createSidecarClient(connection: SidecarConnection) {
  const baseUrl = `http://${connection.host}:${connection.port}`;
  const useIpcFetch =
    typeof window !== "undefined" &&
    window.autoScoring?.sidecarFetch !== undefined;
  const client = createClient<paths>({
    baseUrl,
    ...(useIpcFetch ? { fetch: createIpcSidecarFetch(connection) } : {}),
  });

  const authMiddleware: Middleware = {
    onRequest({ request }) {
      request.headers.set("Authorization", `Bearer ${connection.token}`);
    },
  };
  client.use(authMiddleware);

  return client;
}
