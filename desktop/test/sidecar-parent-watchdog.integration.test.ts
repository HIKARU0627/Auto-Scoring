import { execSync, spawn } from "node:child_process";
import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeAll, beforeEach, describe, expect, it } from "vitest";
import {
  resolveSidecarExecutable,
  sidecarExecutableCandidates,
} from "../src/main/sidecar-paths";
import { SidecarSupervisor } from "../src/main/sidecar-supervisor";
import { applyLinuxKeyringEnvironment } from "./support/linux-keyring-env";

function isProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err: unknown) {
    return (err as { code?: string }).code === "EPERM";
  }
}

async function waitUntil(
  predicate: () => boolean,
  timeoutMs: number,
  intervalMs = 100,
): Promise<number> {
  const start = Date.now();
  const deadline = start + timeoutMs;
  while (Date.now() < deadline) {
    if (predicate()) {
      return Date.now() - start;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error(`Timed out after ${timeoutMs}ms waiting for condition`);
}

describe("Linux CI Parent Process Watchdog Integration (Acceptance 4, UG-01)", () => {
  // Both the `simulated-parent.cjs` helper and the sidecar it starts inherit
  // this process's environment; Linux needs the null keyring backend or startup
  // stalls on D-Bus before `/healthz` (Issue #438).
  beforeAll(() => {
    applyLinuxKeyringEnvironment();
  });

  const isWindows = process.platform === "win32";
  const candidates = sidecarExecutableCandidates({
    resolvedExecutable: process.execPath,
    workingDirectory: path.resolve(__dirname, "../.."),
    isWindows,
  });
  const sidecarExecutable = resolveSidecarExecutable(candidates);

  let tempDir: string;
  let appDataDir: string;
  let markerFile: string;
  let spawnedPids: number[] = [];

  beforeEach(() => {
    // Ensure out/main/sidecar-supervisor.js exists for simulated-parent.cjs
    const supervisorOut = path.resolve(
      __dirname,
      "../out/main/sidecar-supervisor.js",
    );
    if (!fs.existsSync(supervisorOut)) {
      execSync("pnpm run build:main", {
        cwd: path.resolve(__dirname, ".."),
        stdio: "ignore",
      });
    }

    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "watchdog-it-"));
    appDataDir = path.join(tempDir, "app-data");
    markerFile = path.join(tempDir, "marker.json");
    spawnedPids = [];
  });

  afterEach(() => {
    for (const pid of spawnedPids) {
      if (isProcessAlive(pid)) {
        try {
          if (process.platform === "win32") {
            execSync(`taskkill /pid ${pid} /T /F`, { stdio: "ignore" });
          } else {
            process.kill(pid, "SIGKILL");
          }
        } catch {}
      }
    }
    try {
      if (fs.existsSync(tempDir)) {
        fs.rmSync(tempDir, { recursive: true, force: true });
      }
    } catch {}
  });

  it("watched sidecar dies within 5 seconds when parent is killed with SIGKILL (Acceptance 4, UG-01)", async () => {
    expect(sidecarExecutable).not.toBeNull();
    const helperScript = path.resolve(
      __dirname,
      "support/simulated-parent.cjs",
    );

    // 1. Spawn simulated parent process (representing Electron main process)
    const parentProcess = spawn(
      process.execPath,
      [helperScript, sidecarExecutable!, appDataDir, markerFile],
      { stdio: ["ignore", "pipe", "pipe"] },
    );
    spawnedPids.push(parentProcess.pid!);

    // 2. Wait until simulated parent reports sidecar is ready
    await waitUntil(() => fs.existsSync(markerFile), 30_000);
    const marker = JSON.parse(fs.readFileSync(markerFile, "utf8")) as {
      parentPid: number;
      sidecarPid: number;
      host: string;
      port: number;
      token: string;
    };

    spawnedPids.push(marker.sidecarPid);

    // Verify both parent and sidecar are alive
    expect(isProcessAlive(marker.parentPid)).toBe(true);
    expect(isProcessAlive(marker.sidecarPid)).toBe(true);

    // 3. Force-kill the simulated Electron main parent process with SIGKILL (no cleanup handlers run)
    process.kill(marker.parentPid, "SIGKILL");

    // Verify parent is dead
    await waitUntil(() => !isProcessAlive(marker.parentPid), 3000);

    // 4. Acceptance 4: Child sidecar notices parent is dead and exits within 5.0 seconds
    const elapsedMs = await waitUntil(
      () => !isProcessAlive(marker.sidecarPid),
      8000,
      100,
    );

    // #211 specification: DETECTION_BUDGET_SECONDS is 5.0s
    expect(elapsedMs).toBeLessThan(5500);

    // 5. Verify app-data lock is free: a subsequent supervisor can start successfully
    const nextSupervisor = new SidecarSupervisor({
      executablePath: sidecarExecutable!,
      appDataDirectory: appDataDir,
    });
    try {
      await nextSupervisor.start();
      expect(nextSupervisor.status.kind).toBe("ready");
    } finally {
      await nextSupervisor.shutdown();
    }
  });

  it("sidecar started without --parent-pid outlives its parent (Issue #211 req 2)", async () => {
    // When --parent-pid is NOT passed, sidecar does not watch parent (default off)
    expect(sidecarExecutable).not.toBeNull();
    const handshakeDir = fs.mkdtempSync(
      path.join(os.tmpdir(), "handshake-no-watchdog-"),
    );
    const handshakeFile = path.join(handshakeDir, "handshake.json");

    // Spawn an intermediate parent that spawns sidecar WITHOUT --parent-pid
    const intermediateParent = spawn(
      process.execPath,
      [
        "-e",
        `
        const { spawn } = require("node:child_process");
        const fs = require("node:fs");
        const child = spawn(process.argv[1], [
          "--port", "0",
          "--handshake-file", process.argv[2],
          "--app-data-dir", process.argv[3],
        ], { stdio: "ignore", detached: true });
        child.unref();
        fs.writeFileSync(process.argv[4], String(child.pid), "utf8");
        setInterval(() => {}, 1000);
        `,
        sidecarExecutable!,
        handshakeFile,
        appDataDir,
        markerFile,
      ],
      { stdio: "ignore" },
    );
    spawnedPids.push(intermediateParent.pid!);

    await waitUntil(() => fs.existsSync(markerFile), 10_000);
    const unwatchedChildPid = parseInt(fs.readFileSync(markerFile, "utf8"), 10);
    spawnedPids.push(unwatchedChildPid);

    // Wait until handshake is written
    await waitUntil(() => fs.existsSync(handshakeFile), 30_000);
    expect(isProcessAlive(unwatchedChildPid)).toBe(true);

    // Kill intermediate parent with SIGKILL
    intermediateParent.kill("SIGKILL");
    await waitUntil(() => !isProcessAlive(intermediateParent.pid!), 3000);

    // Wait 2 seconds and verify the unwatched child is STILL alive
    await new Promise((r) => setTimeout(r, 2000));
    expect(isProcessAlive(unwatchedChildPid)).toBe(true);

    // Cleanup child
    if (process.platform === "win32") {
      try {
        execSync(`taskkill /pid ${unwatchedChildPid} /T /F`, {
          stdio: "ignore",
        });
      } catch {
        try {
          process.kill(unwatchedChildPid, "SIGKILL");
        } catch {}
      }
    } else {
      try {
        process.kill(unwatchedChildPid, "SIGKILL");
      } catch {}
    }
    try {
      fs.rmSync(handshakeDir, { recursive: true, force: true });
    } catch {}
  });
});
