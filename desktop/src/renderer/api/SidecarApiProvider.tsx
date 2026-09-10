import { createContext, useContext, type JSX, type ReactNode } from "react";

import type { SidecarConnectionInfo } from "../../shared/sidecar-upload.js";
import type { SidecarClient } from "./client.js";

interface SidecarApiContextValue {
  readonly client: SidecarClient | null;
  readonly connection: SidecarConnectionInfo | null;
}

const SidecarApiContext = createContext<SidecarApiContextValue>({
  client: null,
  connection: null,
});

export function SidecarApiProvider({
  client,
  connection = null,
  children,
}: {
  client: SidecarClient | null;
  connection?: SidecarConnectionInfo | null;
  children: ReactNode;
}): JSX.Element {
  return (
    <SidecarApiContext.Provider value={{ client, connection }}>
      {children}
    </SidecarApiContext.Provider>
  );
}

export function useSidecarClient(): SidecarClient {
  const { client } = useContext(SidecarApiContext);
  if (client === null) {
    throw new Error("Sidecar API client is not available");
  }
  return client;
}

export function useSidecarConnection(): SidecarConnectionInfo {
  const { connection } = useContext(SidecarApiContext);
  if (connection === null) {
    throw new Error("Sidecar connection is not available");
  }
  return connection;
}
