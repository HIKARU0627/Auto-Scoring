import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import type { SidecarClient } from "../../src/renderer/api/client.js";
import {
  GradingAvailabilityError,
  loadGradingAvailability,
  useGradingAvailability,
} from "../../src/renderer/core/grading-availability.js";
import { createMockSidecarClient } from "./support/mock-sidecar-client.js";

/**
 * A 200 with an empty body is what the IPC fetch produces when the sidecar
 * answers nothing; `openapi-fetch` reports `data: undefined` and no `error`, so
 * the loader has to treat it as "no answer" rather than hand it to the banner.
 */
describe("loadGradingAvailability", () => {
  it("rejects an empty 200 body instead of returning undefined", async () => {
    const client = {
      GET: async () => ({ data: undefined, error: undefined }),
    } as unknown as SidecarClient;

    await expect(loadGradingAvailability(client)).rejects.toBeInstanceOf(
      GradingAvailabilityError,
    );
  });
});

/**
 * Issue #398: the app shell reads `GET /grading/availability` once per client
 * and hands the answer to `GradingUnavailableBanner`. `null` (never asked, or
 * asked and unanswered) is its own state -- a failed request must not become a
 * configuration accusation (INV-168).
 */
describe("useGradingAvailability", () => {
  it("returns the sidecar's unavailable answer with its reason", async () => {
    const client = createMockSidecarClient({
      getGradingAvailability: async () => ({
        available: false,
        reason: "AI 採点の API キーが未設定です。",
      }),
    });

    const { result } = renderHook(() => useGradingAvailability(client));

    await waitFor(() => {
      expect(result.current).toEqual({
        available: false,
        reason: "AI 採点の API キーが未設定です。",
      });
    });
  });

  it("returns an available answer when this host can grade", async () => {
    const client = createMockSidecarClient({
      getGradingAvailability: async () => ({ available: true }),
    });

    const { result } = renderHook(() => useGradingAvailability(client));

    await waitFor(() => {
      expect(result.current).toEqual({ available: true });
    });
  });

  it("stays null when the request fails: no answer is not 'cannot grade'", async () => {
    const client = createMockSidecarClient({
      getGradingAvailability: async () => {
        throw new Error("sidecar not reachable");
      },
    });

    const { result } = renderHook(() => useGradingAvailability(client));

    await waitFor(() => {
      expect(client.GET).toHaveBeenCalledWith("/grading/availability");
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(result.current).toBeNull();
  });

  it("stays null while no client is connected", () => {
    const { result } = renderHook(() => useGradingAvailability(null));
    expect(result.current).toBeNull();
  });

  it("asks again when the client changes (a sidecar restart)", async () => {
    const first = createMockSidecarClient({
      getGradingAvailability: async () => ({
        available: false,
        reason: "first",
      }),
    });
    const second = createMockSidecarClient({
      getGradingAvailability: async () => ({ available: true }),
    });

    const { result, rerender } = renderHook(
      ({ client }: { client: typeof first }) => useGradingAvailability(client),
      { initialProps: { client: first } },
    );

    await waitFor(() => {
      expect(result.current).toEqual({ available: false, reason: "first" });
    });

    rerender({ client: second });

    await waitFor(() => {
      expect(result.current).toEqual({ available: true });
    });
  });
});
