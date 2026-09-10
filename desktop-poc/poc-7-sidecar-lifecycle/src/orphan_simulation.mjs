import { spawn } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";
import {
  ALREADY_RUNNING_EXIT_CODE,
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

async function main() {
  process.stdout.write(
    "=== PoC 7: Orphan Process & Data Root Lock Simulation ===\n",
  );
  process.stdout.write(`Host Platform: ${process.platform}\n`);

  const executablePath = resolveDefaultSidecarExecutable(REPO_ROOT);
  if (!executablePath) {
    process.stderr.write("Sidecar executable not found.\n");
    process.exit(1);
  }

  const tempAppData = fs.mkdtempSync(
    path.join(os.tmpdir(), "poc7-orphan-standalone-"),
  );
  const markerFile = path.join(
    os.tmpdir(),
    `poc7-marker-standalone-${Date.now()}.json`,
  );

  const simScript = path.join(__dirname, "simulated_main.mjs");
  const child = spawn(process.execPath, [
    simScript,
    REPO_ROOT,
    tempAppData,
    markerFile,
  ]);

  await new Promise((resolve) => {
    child.once("exit", (code, signal) => {
      resolve({ code, signal });
    });
  });

  if (!fs.existsSync(markerFile)) {
    process.stderr.write(
      "Simulated main process failed before writing marker\n",
    );
    process.exit(1);
  }

  const marker = JSON.parse(fs.readFileSync(markerFile, "utf8"));
  const orphanPid = marker.sidecarPid;
  const orphanPort = marker.port;

  process.stdout.write(
    `Simulated main (PID ${marker.parentPid}) killed via SIGKILL.\n`,
  );
  process.stdout.write(
    `Sidecar PID: ${orphanPid}, listening on port: ${orphanPort}\n`,
  );

  const orphanAlive = isProcessAlive(orphanPid);
  process.stdout.write(`Is sidecar still running (orphan)? ${orphanAlive}\n`);

  if (orphanAlive) {
    process.stdout.write(
      "Result on POSIX: Child process is orphaned and keeps running.\n",
    );
    process.stdout.write(
      "Attempting second startup over same app-data directory...\n",
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
      nextSupervisor.state === SidecarState.FAILED &&
      nextSupervisor.failure === SidecarFailure.ALREADY_RUNNING &&
      nextSupervisor.exitCode === ALREADY_RUNNING_EXIT_CODE
    ) {
      process.stdout.write(
        "PASS: Exit code 3 detected -> mapped to ALREADY_RUNNING error screen.\n",
      );
    } else {
      process.stderr.write(
        "FAIL: Did not get expected ALREADY_RUNNING exit code 3.\n",
      );
    }

    // Kill orphan
    try {
      process.kill(orphanPid, "SIGKILL");
      process.stdout.write(`Cleaned up orphan process PID ${orphanPid}.\n`);
    } catch {}
  } else {
    process.stdout.write("Sidecar died when parent terminated.\n");
  }

  fs.rmSync(markerFile, { force: true });
  fs.rmSync(tempAppData, { recursive: true, force: true });
}

main().catch((err) => {
  process.stderr.write(`Error: ${err.message}\n`);
  process.exit(1);
});
