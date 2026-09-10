import type { JSX } from "react";

import { AppShell } from "./AppShell.js";

/**
 * Application entry. The sidecar HTTP client arrives through the lifecycle
 * bridge (Issue #234); until then the shell shows a placeholder title only.
 */
export function App(): JSX.Element {
  return <AppShell client={null} />;
}
