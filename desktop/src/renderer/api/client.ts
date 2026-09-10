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

/** Builds the typed fetch client for `paths` from handshake connection info. */
export function createSidecarClient(connection: SidecarConnection) {
  const baseUrl = `http://${connection.host}:${connection.port}`;
  const client = createClient<paths>({ baseUrl });

  const authMiddleware: Middleware = {
    onRequest({ request }) {
      request.headers.set("Authorization", `Bearer ${connection.token}`);
    },
  };
  client.use(authMiddleware);

  return client;
}
