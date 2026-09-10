import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  ALREADY_RUNNING_EXIT_CODE,
  httpRequest,
  isPortListening,
  resolveDefaultSidecarExecutable,
  SidecarFailure,
  SidecarState,
  SidecarSupervisor,
} from "./sidecar_supervisor.mjs";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const REPO_ROOT = path.resolve(__dirname, "../../..");

function isProcessAlive(pid) {
  try {
    process.kill(pid, 0);
    return true;
  } catch (e) {
    return e.code === "EPERM";
  }
}

async function runStep(name, fn) {
  process.stdout.write(`\n=== [PoC 7 Probe] ${name} ===\n`);
  const start = Date.now();
  try {
    const result = await fn();
    const elapsed = Date.now() - start;
    process.stdout.write(`--> PASSED (${elapsed}ms)\n`);
    return { ok: true, elapsed, result };
  } catch (err) {
    const elapsed = Date.now() - start;
    process.stdout.write(`--> FAILED (${elapsed}ms): ${err.message}\n`);
    return { ok: false, elapsed, error: err };
  }
}

async function testStartupAndHandshake(executablePath, label) {
  const tempAppData = fs.mkdtempSync(
    path.join(os.tmpdir(), "poc7-appdata-startup-"),
  );
  const supervisor = new SidecarSupervisor({
    executablePath,
    appDataDirectory: tempAppData,
    startupTimeoutMs: 30000,
  });

  try {
    const start = Date.now();
    await supervisor.start();
    const startupDurationMs = Date.now() - start;

    if (supervisor.state !== SidecarState.READY) {
      throw new Error(
        `Sidecar did not become READY: ${supervisor.failure} (exit ${supervisor.exitCode})`,
      );
    }

    const { host, port, token, baseUrl } = supervisor.connection;
    if (host !== "127.0.0.1") {
      throw new Error(`Expected host 127.0.0.1, got ${host}`);
    }
    if (port <= 0 || typeof port !== "number") {
      throw new Error(`Expected valid dynamic port > 0, got ${port}`);
    }
    if (!token || typeof token !== "string" || token.length < 16) {
      throw new Error("Token missing or too short");
    }

    // Handshake dir must be deleted immediately after ready
    if (supervisor.handshakeDir && fs.existsSync(supervisor.handshakeDir)) {
      throw new Error(
        `Handshake directory was not deleted: ${supervisor.handshakeDir}`,
      );
    }

    // Probe 1: GET /healthz (unauthenticated, must return 200)
    const healthRes = await httpRequest(`${baseUrl}/healthz`, {
      timeoutMs: 1000,
    });
    if (healthRes.statusCode !== 200) {
      throw new Error(
        `GET /healthz returned ${healthRes.statusCode}, expected 200`,
      );
    }

    // Probe 2: GET /tests with valid Bearer token (must return 200 and JSON array)
    const authRes = await httpRequest(`${baseUrl}/tests`, {
      headers: { Authorization: `Bearer ${token}` },
      timeoutMs: 2000,
    });
    if (authRes.statusCode !== 200) {
      throw new Error(
        `GET /tests returned ${authRes.statusCode}, expected 200`,
      );
    }
    const testsData = JSON.parse(authRes.body);
    if (!Array.isArray(testsData)) {
      throw new Error("GET /tests body is not an array");
    }

    // Probe 3: GET /tests without token (must return 401)
    const unauthRes = await httpRequest(`${baseUrl}/tests`, {
      timeoutMs: 1000,
    });
    if (unauthRes.statusCode !== 401) {
      throw new Error(
        `GET /tests without token returned ${unauthRes.statusCode}, expected 401`,
      );
    }

    // Probe 4: GET /tests with invalid token (must return 401)
    const badAuthRes = await httpRequest(`${baseUrl}/tests`, {
      headers: { Authorization: "Bearer bad-invalid-token" },
      timeoutMs: 1000,
    });
    if (badAuthRes.statusCode !== 401) {
      throw new Error(
        `GET /tests with bad token returned ${badAuthRes.statusCode}, expected 401`,
      );
    }

    process.stdout.write(
      `[${label}] Startup time: ${startupDurationMs}ms | Assigned port: ${port} | Token length: ${token.length} chars (value redacted)\n`,
    );

    return { startupDurationMs, port };
  } finally {
    await supervisor.shutdown();
    fs.rmSync(tempAppData, { recursive: true, force: true });
  }
}

async function testShutdown(executablePath) {
  const tempAppData = fs.mkdtempSync(
    path.join(os.tmpdir(), "poc7-appdata-shutdown-"),
  );
  const supervisor = new SidecarSupervisor({
    executablePath,
    appDataDirectory: tempAppData,
  });

  await supervisor.start();
  if (supervisor.state !== SidecarState.READY) {
    throw new Error(`Failed to start: ${supervisor.failure}`);
  }

  const pid = supervisor.childProcess.pid;
  const port = supervisor.connection.port;

  if (!isProcessAlive(pid)) {
    throw new Error(`Sidecar process ${pid} not alive before shutdown`);
  }
  const listeningBefore = await isPortListening(port);
  if (!listeningBefore) {
    throw new Error(`Port ${port} not listening before shutdown`);
  }

  const startShutdown = Date.now();
  await supervisor.shutdown();
  const shutdownDurationMs = Date.now() - startShutdown;

  if (supervisor.state !== SidecarState.STOPPED) {
    throw new Error(`Expected state STOPPED, got ${supervisor.state}`);
  }

  // 1. Check process is no longer running
  const aliveAfter = isProcessAlive(pid);
  if (aliveAfter) {
    throw new Error(`Process ${pid} is still alive after shutdown!`);
  }

  // 2. Check port is no longer listening
  const listeningAfter = await isPortListening(port);
  if (listeningAfter) {
    throw new Error(`Port ${port} is still listening after shutdown!`);
  }

  // 3. Check app-data lock is released: start second instance on same app-data
  const secondSupervisor = new SidecarSupervisor({
    executablePath,
    appDataDirectory: tempAppData,
  });
  await secondSupervisor.start();
  if (secondSupervisor.state !== SidecarState.READY) {
    throw new Error(
      `Second supervisor failed to acquire app-data lock: ${secondSupervisor.failure}`,
    );
  }
  await secondSupervisor.shutdown();

  process.stdout.write(
    `Shutdown duration: ${shutdownDurationMs}ms | Process PID ${pid} dead: true | Port ${port} closed: true | Lock released: true\n`,
  );

  fs.rmSync(tempAppData, { recursive: true, force: true });
  return { shutdownDurationMs };
}

async function testOrphanAndLockBehavior(executablePath) {
  const tempAppData = fs.mkdtempSync(
    path.join(os.tmpdir(), "poc7-appdata-orphan-"),
  );
  const markerFile = path.join(os.tmpdir(), `poc7-marker-${Date.now()}.json`);

  const simScript = path.join(__dirname, "simulated_main.mjs");
  const child = spawn(process.execPath, [
    simScript,
    REPO_ROOT,
    tempAppData,
    markerFile,
  ]);

  // Wait for simulated main to write marker and kill itself with SIGKILL
  await new Promise((resolve) => {
    child.once("exit", (code, signal) => {
      resolve({ code, signal });
    });
  });

  if (!fs.existsSync(markerFile)) {
    throw new Error("Simulated main process failed before writing marker file");
  }

  const marker = JSON.parse(fs.readFileSync(markerFile, "utf8"));
  const orphanPid = marker.sidecarPid;
  const orphanPort = marker.port;

  process.stdout.write(
    `Simulated main (PID ${marker.parentPid}) killed with SIGKILL.\n`,
  );
  process.stdout.write(
    `Checking sidecar child (PID ${orphanPid}, port ${orphanPort})...\n`,
  );

  const orphanAlive = isProcessAlive(orphanPid);
  process.stdout.write(`Is sidecar still alive (orphan)? ${orphanAlive}\n`);

  if (!orphanAlive) {
    process.stdout.write("Note: Sidecar did not survive parent kill.\n");
  } else {
    process.stdout.write(
      "CONFIRMED: On POSIX/Linux without Job Objects or PR_SET_PDEATHSIG, sidecar survives as an orphan!\n",
    );

    // Test what happens when next app instance starts on the same app-data
    process.stdout.write(
      "Starting second supervisor instance on the same app-data directory...\n",
    );
    const nextSupervisor = new SidecarSupervisor({
      executablePath,
      appDataDirectory: tempAppData,
      startupTimeoutMs: 10000,
    });

    await nextSupervisor.start();
    process.stdout.write(
      `Second supervisor state: ${nextSupervisor.state} | failure: ${nextSupervisor.failure} | exitCode: ${nextSupervisor.exitCode}\n`,
    );

    if (
      nextSupervisor.state !== SidecarState.FAILED ||
      nextSupervisor.failure !== SidecarFailure.ALREADY_RUNNING ||
      nextSupervisor.exitCode !== ALREADY_RUNNING_EXIT_CODE
    ) {
      throw new Error(
        `Expected failure ALREADY_RUNNING with exitCode 3, got ${nextSupervisor.failure} with exitCode ${nextSupervisor.exitCode}`,
      );
    }
    process.stdout.write(
      "CONFIRMED: Next startup immediately rejected with exit code 3 (ALREADY_RUNNING) due to app-data lock!\n",
    );

    // Clean up orphan process
    try {
      process.kill(orphanPid, "SIGKILL");
    } catch {}
  }

  fs.rmSync(markerFile, { force: true });
  fs.rmSync(tempAppData, { recursive: true, force: true });
  return { orphanAlive };
}

async function testRestart(executablePath) {
  const tempAppData = fs.mkdtempSync(
    path.join(os.tmpdir(), "poc7-appdata-restart-"),
  );
  const supervisor = new SidecarSupervisor({
    executablePath,
    appDataDirectory: tempAppData,
  });

  try {
    // 1. Initial start
    await supervisor.start();
    if (supervisor.state !== SidecarState.READY) {
      throw new Error(`Initial start failed: ${supervisor.failure}`);
    }
    const firstPort = supervisor.connection.port;
    const firstToken = supervisor.connection.token;
    const firstPid = supervisor.childProcess.pid;

    process.stdout.write(
      `First run: PID ${firstPid}, Port ${firstPort}, Token len ${firstToken.length}\n`,
    );

    // 2. Restart (call start() again)
    const restartStart = Date.now();
    await supervisor.start();
    const restartDurationMs = Date.now() - restartStart;

    if (supervisor.state !== SidecarState.READY) {
      throw new Error(`Restart failed: ${supervisor.failure}`);
    }

    const secondPort = supervisor.connection.port;
    const secondToken = supervisor.connection.token;
    const secondPid = supervisor.childProcess.pid;

    process.stdout.write(
      `Restart run: PID ${secondPid}, Port ${secondPort}, Token len ${secondToken.length} (in ${restartDurationMs}ms)\n`,
    );

    if (firstPid === secondPid) {
      throw new Error("Expected new process PID after restart");
    }
    if (firstToken === secondToken) {
      throw new Error("Expected fresh token after restart");
    }

    // Verify first process is dead
    if (isProcessAlive(firstPid)) {
      throw new Error(`First process PID ${firstPid} is still alive!`);
    }

    // Verify second instance is healthy and authenticated
    const health = await httpRequest(
      `${supervisor.connection.baseUrl}/healthz`,
    );
    if (health.statusCode !== 200) {
      throw new Error(
        `Health probe on restart port failed: ${health.statusCode}`,
      );
    }

    const authed = await supervisor.probeAuthenticated();
    if (authed.statusCode !== 200) {
      throw new Error(
        `Auth probe on restart port failed: ${authed.statusCode}`,
      );
    }

    return { restartDurationMs, firstPort, secondPort };
  } finally {
    await supervisor.shutdown();
    fs.rmSync(tempAppData, { recursive: true, force: true });
  }
}

async function testFlakyShutdownParity(executablePath, iterations = 10) {
  process.stdout.write(
    `Running ${iterations} consecutive start/shutdown cycles to observe port/process release...\n`,
  );
  const tempAppData = fs.mkdtempSync(
    path.join(os.tmpdir(), "poc7-appdata-flake-"),
  );
  let anomalies = 0;

  for (let i = 1; i <= iterations; i++) {
    const supervisor = new SidecarSupervisor({
      executablePath,
      appDataDirectory: tempAppData,
      startupTimeoutMs: 15000,
    });

    await supervisor.start();
    if (supervisor.state !== SidecarState.READY) {
      throw new Error(`Cycle ${i} failed to start: ${supervisor.failure}`);
    }

    const pid = supervisor.childProcess.pid;
    const port = supervisor.connection.port;
    const token = supervisor.connection.token;

    await supervisor.shutdown();

    const processAlive = isProcessAlive(pid);
    const portListening = await isPortListening(port);

    let tokenStillAccepted = false;
    if (portListening) {
      try {
        const res = await httpRequest(`http://127.0.0.1:${port}/tests`, {
          headers: { Authorization: `Bearer ${token}` },
          timeoutMs: 500,
        });
        if (res.statusCode === 200) {
          tokenStillAccepted = true;
        }
      } catch {}
    }

    if (processAlive || portListening || tokenStillAccepted) {
      anomalies++;
      process.stdout.write(
        `Cycle ${i}: ANOMALY DETECTED! processAlive=${processAlive}, portListening=${portListening}, tokenStillAccepted=${tokenStillAccepted}\n`,
      );
    } else {
      process.stdout.write(`Cycle ${i}/${iterations}: OK\n`);
    }
  }

  fs.rmSync(tempAppData, { recursive: true, force: true });
  return { iterations, anomalies };
}

async function main() {
  process.stdout.write(
    "====================================================\n",
  );
  process.stdout.write(
    "PoC 7: Sidecar Lifecycle Technical Probe (Node/Electron)\n",
  );
  process.stdout.write(
    `Host Platform: ${process.platform} (${process.arch})\n`,
  );
  process.stdout.write(`Node Version: ${process.version}\n`);
  process.stdout.write(
    "====================================================\n",
  );

  const pyinstallerPath = path.join(
    REPO_ROOT,
    "backend",
    "dist",
    "auto-scoring-sidecar",
    "auto-scoring-sidecar",
  );
  const venvPath = path.join(
    REPO_ROOT,
    "backend",
    ".venv",
    "bin",
    "auto-scoring-sidecar",
  );

  const hasPyInstaller = fs.existsSync(pyinstallerPath);
  const hasVenv = fs.existsSync(venvPath);

  process.stdout.write(
    `PyInstaller binary exists: ${hasPyInstaller} (${pyinstallerPath})\n`,
  );
  process.stdout.write(
    `venv console script exists: ${hasVenv} (${venvPath})\n`,
  );

  const targetExe = hasPyInstaller ? pyinstallerPath : venvPath;
  const targetLabel = hasPyInstaller
    ? "PyInstaller Bundle"
    : "Venv Console Script";

  process.stdout.write(
    `Using target executable: ${targetExe} (${targetLabel})\n`,
  );

  // Item 1: 起動と handshake
  await runStep("1. 起動と handshake (PyInstaller / Target)", () =>
    testStartupAndHandshake(targetExe, targetLabel),
  );

  if (hasPyInstaller && hasVenv) {
    await runStep("1b. 起動と handshake (Venv Script)", () =>
      testStartupAndHandshake(venvPath, "Venv Console Script"),
    );
  }

  // Item 2: 終了 (通常終了)
  await runStep("2. 通常終了 (プロセス消滅・ポート解放・ロック解放)", () =>
    testShutdown(targetExe),
  );

  // Item 3: 異常系（強制終了と孤児・二重起動ロック）
  await runStep("3. 異常系 (親プロセスキル時の孤児化とapp-dataロック)", () =>
    testOrphanAndLockBehavior(targetExe),
  );

  // Item 4: 再起動 (設定変更時の再起動)
  await runStep("4. 再起動 (プロセス置換・新ポート新トークン・即時反映)", () =>
    testRestart(targetExe),
  );

  // Item 5: 既知の弱点 (#57 parity check)
  await runStep(
    "5. 既知の弱点 (#57: shutdown時のポート解放の整合性 10回試行)",
    () => testFlakyShutdownParity(targetExe, 10),
  );

  process.stdout.write("\n=== All PoC 7 Probe Measurements Completed ===\n");
}

main().catch((err) => {
  process.stderr.write(`Probe execution failed: ${err.stack || err}\n`);
  process.exit(1);
});
