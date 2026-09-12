import { useEffect, useState } from "react";

import type { SidecarClient } from "../api/client.js";
import type { components } from "../api/generated/schema.js";

/**
 * The sidecar's answer to `GET /grading/availability` (Issue #97, #398).
 *
 * `null` is a distinct state, not "assume it works": the banner shows nothing
 * for it, so one failed request never turns into an announcement that the
 * machine is misconfigured.
 */
export type GradingAvailability =
  components["schemas"]["GradingAvailabilityResponse"];

export class GradingAvailabilityError extends Error {}

/** Asks the sidecar once whether this host can AI-grade. */
export async function loadGradingAvailability(
  client: SidecarClient,
): Promise<GradingAvailability> {
  const response = await client.GET("/grading/availability");
  // `data === undefined` with no `error` is what a 200 with an empty body
  // produces: still "we could not ask", not an answer (INV-168).
  if (response.error !== undefined || response.data === undefined) {
    throw new GradingAvailabilityError("AI 採点の利用可否を取得できません");
  }
  return response.data;
}

/**
 * Reads `GET /grading/availability` once per client (Issue #398).
 *
 * The app shell calls this with the client the supervisor established, so the
 * answer is dropped and asked again whenever that client changes (a sidecar
 * restart, a reconnection). A failed request is swallowed on purpose: every
 * screen already reports its own request failures, and "we could not ask" must
 * leave the answer `null`, which shows no banner at all -- the same rule
 * `GradingUnavailableBanner` states (INV-168).
 */
export function useGradingAvailability(
  client: SidecarClient | null,
): GradingAvailability | null {
  const [availability, setAvailability] = useState<GradingAvailability | null>(
    null,
  );

  useEffect(() => {
    if (client === null) {
      setAvailability(null);
      return;
    }
    let active = true;
    setAvailability(null);
    loadGradingAvailability(client)
      .then((result) => {
        if (active) {
          setAvailability(result);
        }
      })
      .catch(() => {
        // Not connected, timed out, or an older sidecar without the endpoint:
        // an unanswered question is not a "this machine cannot grade".
      });
    return () => {
      active = false;
    };
  }, [client]);

  return availability;
}
