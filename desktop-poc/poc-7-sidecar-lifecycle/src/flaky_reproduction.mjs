import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  httpRequest,
  isPortListening,
  resolveDefaultSidecarExecutable,
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

async function main() {
  const iterations = parseInt(process.argv[2] || "50", 10);
  process.stdout.write(
    `=== PoC 7: Flaky Shutdown & Port Release Stress Test (${iterations} iterations) ===\n`,
  );
  process.stdout.write(`Host Platform: ${process.platform}\n`);

  const executablePath = resolveDefaultSidecarExecutable(REPO_ROOT);
  if (!executablePath) {
    process.stderr.write("No sidecar executable found.\n");
    process.exit(1);
  }
  process.stdout.write(`Executable: ${executablePath}\n`);

  const tempAppData = fs.mkdtempSync(
    path.join(os.tmpdir(), "poc7-flake-stress-"),
  );
  let anomalies = 0;
  const timings = [];

  for (let i = 1; i <= iterations; i++) {
    const supervisor = new SidecarSupervisor({
      executablePath,
      appDataDirectory: tempAppData,
      startupTimeoutMs: 15000,
    });

    const start = Date.now();
    await supervisor.start();
    const startupMs = Date.now() - start;

    if (supervisor.state !== SidecarState.READY) {
      process.stderr.write(`Iteration ${i}: failed to start!\n`);
      anomalies++;
      continue;
    }

    const pid = supervisor.childProcess.pid;
    const port = supervisor.connection.port;
    const token = supervisor.connection.token;

    // Immediately shutdown
    const shutdownStart = Date.now();
    await supervisor.shutdown();
    const shutdownMs = Date.now() - shutdownStart;

    timings.push({ startupMs, shutdownMs });

    // Immediate check
    const alive = isProcessAlive(pid);
    const listening = await isPortListening(port);
    let tokenAccepted = false;

    if (listening) {
      try {
        const res = await httpRequest(`http://127.0.0.1:${port}/tests`, {
          headers: { Authorization: `Bearer ${token}` },
          timeoutMs: 300,
        });
        if (res.statusCode === 200) {
          tokenAccepted = true;
        }
      } catch {}
    }

    if (alive || listening || tokenAccepted) {
      anomalies++;
      process.stdout.write(
        `Iteration ${i}/${iterations}: ANOMALY DETECTED! (alive=${alive}, listening=${listening}, tokenAccepted=${tokenAccepted})\n`,
      );
    } else {
      if (i % 10 === 0 || i === iterations) {
        process.stdout.write(
          `Iteration ${i}/${iterations}: OK (last startup: ${startupMs}ms, shutdown: ${shutdownMs}ms)\n`,
        );
      }
    }
  }

  fs.rmSync(tempAppData, { recursive: true, force: true });

  const avgStartup =
    timings.reduce((sum, t) => sum + t.startupMs, 0) / (timings.length || 1);
  const avgShutdown =
    timings.reduce((sum, t) => sum + t.shutdownMs, 0) / (timings.length || 1);

  process.stdout.write("\n--- Summary ---\n");
  process.stdout.write(`Total iterations: ${iterations}\n`);
  process.stdout.write(`Anomalies detected: ${anomalies}\n`);
  process.stdout.write(`Avg startup time: ${avgStartup.toFixed(1)}ms\n`);
  process.stdout.write(`Avg shutdown time: ${avgShutdown.toFixed(1)}ms\n`);
}

main().catch((err) => {
  process.stderr.write(`Flake stress test failed: ${err.message}\n`);
  process.exit(1);
});
