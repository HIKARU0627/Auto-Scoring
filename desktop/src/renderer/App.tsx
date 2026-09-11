import { useEffect, useMemo, useState, type JSX } from "react";

import type { SidecarStatus } from "../shared/bridge.js";
import { AppShell } from "./AppShell.js";
import { createSidecarClient } from "./api/client.js";
import { SidecarStartupOverlay } from "./features/startup/SidecarStartupOverlay.js";

/**
 * Application entry. Subscribes to the sidecar lifecycle bridge (Issue #234)
 * and hands a typed HTTP client to the shell once the sidecar is ready.
 */
export function App(): JSX.Element {
  const [status, setStatus] = useState<SidecarStatus>({ kind: "starting" });

  useEffect(() => {
    const bridge = window.autoScoring;
    if (bridge === undefined) {
      return;
    }

    void bridge.getSidecarStatus().then(setStatus);
    return bridge.onSidecarStatusChange(setStatus);
  }, []);

  const client = useMemo(() => {
    if (status.kind !== "ready") {
      return null;
    }
    return createSidecarClient(status.connection);
  }, [status]);

  const connection = status.kind === "ready" ? status.connection : null;

  const handleRestart = (): void => {
    void window.autoScoring?.restartSidecar();
  };

  return (
    <SidecarStartupOverlay status={status} onRestart={handleRestart}>
      <AppShell client={client} connection={connection} />
    </SidecarStartupOverlay>
  );
}
