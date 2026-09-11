import * as fs from "node:fs";
import * as http from "node:http";
import * as net from "node:net";
import * as os from "node:os";
import * as path from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import {
  SIDECAR_ALREADY_RUNNING_EXIT_CODE,
  SidecarSupervisor,
} from "../src/main/sidecar-supervisor";
import {
  resolveSidecarExecutable,
  sidecarExecutableCandidates,
} from "../src/main/sidecar-paths";

function isProcessAlive(pid: number): boolean {
  try {
    process.kill(pid, 0);
    return true;
  } catch (err: unknown) {
    return (err as { code?: string }).code === "EPERM";
  }
}

async function waitUntil(
  predicate: () => boolean | Promise<boolean>,
  timeoutMs: number,
  intervalMs = 100,
): Promise<number> {
  const start = Date.now();
  const deadline = start + timeoutMs;
  while (Date.now() < deadline) {
    if (await predicate()) {
      return Date.now() - start;
    }
    await new Promise((resolve) => setTimeout(resolve, intervalMs));
  }
  throw new Error(`Timed out after ${timeoutMs}ms waiting for condition`);
}

function isPortListening(
  port: number,
  host = "127.0.0.1",
  timeoutMs = 500,
): Promise<boolean> {
  return new Promise((resolve) => {
    const socket = new net.Socket();
    let connected = false;
    socket.setTimeout(timeoutMs);
    socket.once("connect", () => {
      connected = true;
      socket.destroy();
    });
    socket.once("timeout", () => {
      socket.destroy();
      resolve(false);
    });
    socket.once("error", () => {
      resolve(false);
    });
    socket.once("close", () => {
      resolve(connected);
    });
    socket.connect(port, host);
  });
}

function httpRequest(
  urlStr: string,
  options: {
    method?: string;
    headers?: Record<string, string>;
    timeoutMs?: number;
  } = {},
): Promise<{ statusCode?: number | undefined; body: string }> {
  return new Promise((resolve, reject) => {
    const url = new URL(urlStr);
    const req = http.request(
      url,
      {
        method: options.method ?? "GET",
        headers: options.headers ?? {},
        timeout: options.timeoutMs ?? 2000,
      },
      (res) => {
        let body = "";
        res.setEncoding("utf8");
        res.on("data", (chunk) => {
          body += chunk;
        });
        res.on("end", () => {
          resolve({ statusCode: res.statusCode, body });
        });
      },
    );
    req.on("timeout", () => {
      req.destroy();
      reject(new Error(`Timeout requesting ${urlStr}`));
    });
    req.on("error", reject);
    req.end();
  });
}

describe("SidecarSupervisor integration tests", () => {
  const isWindows = process.platform === "win32";
  const candidates = sidecarExecutableCandidates({
    resolvedExecutable: process.execPath,
    workingDirectory: path.resolve(__dirname, "../.."),
    isWindows,
  });
  const sidecarExecutable = resolveSidecarExecutable(candidates);

  let tempDir: string;
  let appDataDir: string;

  beforeEach(() => {
    tempDir = fs.mkdtempSync(path.join(os.tmpdir(), "supervisor-it-"));
    appDataDir = path.join(tempDir, "app-data");
  });

  afterEach(() => {
    try {
      if (fs.existsSync(tempDir)) {
        fs.rmSync(tempDir, { recursive: true, force: true });
      }
    } catch {
      // Best-effort cleanup
    }
  });

  it("starts real sidecar on dynamic port, verifies health and auth, and cleans handshake (Acceptance 1, INV-044)", async () => {
    expect(sidecarExecutable).not.toBeNull();
    const supervisor = new SidecarSupervisor({
      executablePath: sidecarExecutable,
      appDataDirectory: appDataDir,
    });

    try {
      await supervisor.start();
      expect(supervisor.status.kind).toBe("ready");
      if (supervisor.status.kind !== "ready") {
        return;
      }

      const connection =
        supervisor.internalStatus.kind === "ready"
          ? supervisor.internalStatus.connection
          : null;
      expect(connection).not.toBeNull();
      if (connection === null) {
        return;
      }
      expect(connection.host).toBe("127.0.0.1");
      expect(connection.port).toBeGreaterThan(0);
      expect(connection.token).toBeTruthy();
      expect(supervisor.status.connection).not.toHaveProperty("token");

      const pid = supervisor.processHandle?.pid;
      expect(pid).toBeDefined();
      expect(isProcessAlive(pid!)).toBe(true);

      // Acceptance 1: /healthz passes without token
      const healthRes = await httpRequest(
        `http://${connection.host}:${connection.port}/healthz`,
      );
      expect(healthRes.statusCode).toBe(200);

      // INV-044 / INV-047: Protected API succeeds with token
      const testsWithToken = await httpRequest(
        `http://${connection.host}:${connection.port}/tests`,
        {
          headers: { Authorization: `Bearer ${connection.token}` },
        },
      );
      expect(testsWithToken.statusCode).toBe(200);
      expect(JSON.parse(testsWithToken.body)).toEqual([]);

      // Protected API fails without token (401)
      const testsNoToken = await httpRequest(
        `http://${connection.host}:${connection.port}/tests`,
      );
      expect(testsNoToken.statusCode).toBe(401);

      // Protected API fails with invalid token (401)
      const testsBadToken = await httpRequest(
        `http://${connection.host}:${connection.port}/tests`,
        {
          headers: { Authorization: "Bearer bogus-token" },
        },
      );
      expect(testsBadToken.statusCode).toBe(401);

      // INV-038: Handshake directory deleted after ready
      const leftOverHandshakeDirs = fs
        .readdirSync(os.tmpdir())
        .filter((d) => d.startsWith("auto-scoring-handshake-"));
      // Ensure none of the leftover directories contain a handshake.json matching our port
      for (const d of leftOverHandshakeDirs) {
        const hFile = path.join(os.tmpdir(), d, "handshake.json");
        if (fs.existsSync(hFile)) {
          const content = fs.readFileSync(hFile, "utf8");
          expect(content).not.toContain(String(connection.port));
        }
      }
    } finally {
      await supervisor.shutdown();
    }
  });

  it("shutdown cleanly terminates process, closes port, and releases lock (Acceptance 2, INV-045)", async () => {
    expect(sidecarExecutable).not.toBeNull();
    const supervisor = new SidecarSupervisor({
      executablePath: sidecarExecutable,
      appDataDirectory: appDataDir,
    });

    await supervisor.start();
    expect(supervisor.status.kind).toBe("ready");
    if (supervisor.status.kind !== "ready") {
      return;
    }

    const { host, port } = supervisor.status.connection;
    const pid = supervisor.processHandle?.pid!;
    expect(isProcessAlive(pid)).toBe(true);
    expect(await isPortListening(port, host)).toBe(true);

    // Perform shutdown
    await supervisor.shutdown();
    expect(supervisor.status.kind).toBe("stopped");

    // Acceptance 2: Process is dead
    expect(isProcessAlive(pid)).toBe(false);

    // Acceptance 2: Port is released (connection refused)
    const portReleased = await waitUntil(
      async () => !(await isPortListening(port, host)),
      5000,
      100,
    )
      .then(() => true)
      .catch(() => false);
    expect(portReleased).toBe(true);

    // Acceptance 2: App-data lock released, so a second supervisor can start immediately
    const nextSupervisor = new SidecarSupervisor({
      executablePath: sidecarExecutable,
      appDataDirectory: appDataDir,
    });
    try {
      await nextSupervisor.start();
      expect(nextSupervisor.status.kind).toBe("ready");
    } finally {
      await nextSupervisor.shutdown();
    }
  });

  it("restarts cleanly over the same app-data directory (INV-032)", async () => {
    expect(sidecarExecutable).not.toBeNull();
    const supervisor = new SidecarSupervisor({
      executablePath: sidecarExecutable,
      appDataDirectory: appDataDir,
    });

    try {
      await supervisor.start();
      expect(supervisor.status.kind).toBe("ready");
      if (supervisor.status.kind !== "ready") return;

      const firstPort = supervisor.status.connection.port;
      const firstPid = supervisor.processHandle?.pid!;
      expect(firstPort).toBeGreaterThan(0);

      await supervisor.restart();
      expect(supervisor.status.kind).toBe("ready");
      if (supervisor.status.kind !== "ready") return;

      const secondPort = supervisor.status.connection.port;
      const secondPid = supervisor.processHandle?.pid!;

      expect(isProcessAlive(firstPid)).toBe(false);
      expect(isProcessAlive(secondPid)).toBe(true);
      expect(secondPort).toBeGreaterThan(0);

      const healthRes = await httpRequest(
        `http://${supervisor.status.connection.host}:${secondPort}/healthz`,
      );
      expect(healthRes.statusCode).toBe(200);
    } finally {
      await supervisor.shutdown();
    }
  });

  it("second instance fails with exit code 3 alreadyRunning when locked (Acceptance 3, INV-034, INV-040)", async () => {
    expect(sidecarExecutable).not.toBeNull();
    const supervisor1 = new SidecarSupervisor({
      executablePath: sidecarExecutable,
      appDataDirectory: appDataDir,
    });

    await supervisor1.start();
    expect(supervisor1.status.kind).toBe("ready");

    const supervisor2 = new SidecarSupervisor({
      executablePath: sidecarExecutable,
      appDataDirectory: appDataDir,
      startupTimeoutMs: 10_000,
    });

    try {
      const startSecondTime = Date.now();
      await supervisor2.start();
      const elapsed = Date.now() - startSecondTime;

      // Acceptance 3: exit code 3 immediately detected without waiting 10s timeout
      expect(supervisor2.status.kind).toBe("failed");
      if (supervisor2.status.kind === "failed") {
        expect(supervisor2.status.failure).toBe("alreadyRunning");
        expect(supervisor2.status.exitCode).toBe(
          SIDECAR_ALREADY_RUNNING_EXIT_CODE,
        );
      }
      expect(elapsed).toBeLessThan(5000);
    } finally {
      await supervisor1.shutdown();
      await supervisor2.shutdown();
    }
  });
});
