import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { fileURLToPath } from "node:url";
import {
  ALREADY_RUNNING_EXIT_CODE,
  httpRequest,
  isPortListening,
  resolveDefaultSidecarExecutable,
  SidecarFailure,
  SidecarState,
  SidecarSupervisor,
} from "../src/sidecar_supervisor.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "../../..");

test("SidecarSupervisor - reports EXECUTABLE_MISSING when binary not found", async () => {
  const supervisor = new SidecarSupervisor({
    executablePath: "/path/to/nonexistent-sidecar-binary",
  });
  await supervisor.start();
  assert.equal(supervisor.state, SidecarState.FAILED);
  assert.equal(supervisor.failure, SidecarFailure.EXECUTABLE_MISSING);
});

test("SidecarSupervisor - full lifecycle with live sidecar", async () => {
  const executable = resolveDefaultSidecarExecutable(REPO_ROOT);
  assert.ok(executable, "Executable should be found in repo");

  const tempAppData = fs.mkdtempSync(
    path.join(os.tmpdir(), "poc7-unit-appdata-"),
  );
  const supervisor = new SidecarSupervisor({
    executablePath: executable,
    appDataDirectory: tempAppData,
    startupTimeoutMs: 30000,
  });

  try {
    // 1. Startup & Handshake
    await supervisor.start();
    assert.equal(supervisor.state, SidecarState.READY);
    assert.ok(supervisor.connection.port > 0);
    assert.equal(supervisor.connection.host, "127.0.0.1");
    assert.ok(supervisor.connection.token.length > 0);

    // 2. Health & Auth probe
    const health = await httpRequest(
      `${supervisor.connection.baseUrl}/healthz`,
    );
    assert.equal(health.statusCode, 200);

    const authed = await supervisor.probeAuthenticated();
    assert.equal(authed.statusCode, 200);

    // 3. Reject second instance over same app-data (app-data lock)
    const second = new SidecarSupervisor({
      executablePath: executable,
      appDataDirectory: tempAppData,
      startupTimeoutMs: 10000,
    });
    await second.start();
    assert.equal(second.state, SidecarState.FAILED);
    assert.equal(second.failure, SidecarFailure.ALREADY_RUNNING);
    assert.equal(second.exitCode, ALREADY_RUNNING_EXIT_CODE);

    // 4. Shutdown
    const port = supervisor.connection.port;
    await supervisor.shutdown();
    assert.equal(supervisor.state, SidecarState.STOPPED);

    // Port should be closed
    const listening = await isPortListening(port);
    assert.equal(listening, false);

    // 5. Restart after shutdown over same app-data succeeds
    await second.start();
    assert.equal(second.state, SidecarState.READY);
    await second.shutdown();
  } finally {
    await supervisor.shutdown();
    fs.rmSync(tempAppData, { recursive: true, force: true });
  }
});
