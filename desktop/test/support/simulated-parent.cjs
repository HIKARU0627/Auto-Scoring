const fs = require("node:fs");
const path = require("node:path");

/**
 * Helper process representing the Electron main process.
 * Spawns SidecarSupervisor (which passes --parent-pid process.pid to sidecar),
 * writes details to marker file once ready, and parks indefinitely.
 */
async function main() {
  const [sidecarExecutable, appDataDir, markerFile] = process.argv.slice(2);
  if (!sidecarExecutable || !appDataDir || !markerFile) {
    process.stderr.write(
      "Usage: node simulated-parent.cjs <sidecarExe> <appDataDir> <markerFile>\n",
    );
    process.exit(1);
  }

  const supervisorPath = path.resolve(
    __dirname,
    "../../out/main/sidecar-supervisor.js",
  );
  const { SidecarSupervisor } = require(supervisorPath);

  const supervisor = new SidecarSupervisor({
    executablePath: sidecarExecutable,
    appDataDirectory: appDataDir,
  });

  await supervisor.start();
  if (supervisor.status.kind !== "ready") {
    process.stderr.write(
      `Failed to start sidecar: ${supervisor.status.kind}\n`,
    );
    process.exit(1);
  }

  const connection = supervisor.status.connection;
  const sidecarPid = supervisor.processHandle.pid;

  fs.writeFileSync(
    markerFile,
    JSON.stringify({
      parentPid: process.pid,
      sidecarPid,
      host: connection.host,
      port: connection.port,
      token: connection.token,
    }),
    "utf8",
  );

  // Keep parent alive until forcibly killed by the test
  setInterval(() => {}, 1000);
}

main().catch((err) => {
  process.stderr.write(`simulated-parent error: ${err.message}\n`);
  process.exit(1);
});
