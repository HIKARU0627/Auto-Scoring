import { createContext, useContext, type JSX, type ReactNode } from "react";

import type { SidecarClient } from "./client.js";

interface SidecarApiContextValue {
  readonly client: SidecarClient | null;
}

const SidecarApiContext = createContext<SidecarApiContextValue>({
  client: null,
});

export function SidecarApiProvider({
  client,
  children,
}: {
  client: SidecarClient | null;
  children: ReactNode;
}): JSX.Element {
  return (
    <SidecarApiContext.Provider value={{ client }}>
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
