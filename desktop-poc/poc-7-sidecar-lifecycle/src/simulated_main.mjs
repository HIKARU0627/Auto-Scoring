import fs from "node:fs";
import {
  SidecarSupervisor,
  resolveDefaultSidecarExecutable,
} from "./sidecar_supervisor.mjs";

/**
 * Simulates Electron main process:
 * 1. Starts sidecar supervisor
 * 2. Waits for sidecar to become READY
 * 3. Writes PID of sidecar to stdout / file so probe runner knows it
 * 4. Forcibly terminates itself (SIGKILL / exit without cleanup)
 */
async function main() {
  const repoRoot = process.argv[2];
  const appDataDir = process.argv[3];
  const markerFile = process.argv[4];

  const executablePath = resolveDefaultSidecarExecutable(repoRoot);
  const supervisor = new SidecarSupervisor({
    executablePath,
    appDataDirectory: appDataDir,
  });

  await supervisor.start();
  if (supervisor.state !== "READY") {
    process.stderr.write(`Failed to start sidecar: ${supervisor.failure}\n`);
    process.exit(1);
  }

  const sidecarPid = supervisor.childProcess.pid;
  const port = supervisor.connection.port;
  const token = supervisor.connection.token;

  // Record details to marker file
  fs.writeFileSync(
    markerFile,
    JSON.stringify({
      parentPid: process.pid,
      sidecarPid,
      port,
      token,
    }),
    "utf8",
  );

  // Crash / force-kill simulated Electron main process immediately
  process.kill(process.pid, "SIGKILL");
}

main().catch((err) => {
  process.stderr.write(`simulated_main error: ${err.message}\n`);
  process.exit(1);
});
