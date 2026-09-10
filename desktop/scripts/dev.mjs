/**
 * Runs the renderer's Vite dev server and points a live Electron window at it.
 *
 * Two processes have to agree on one URL, and Vite picks the port at runtime, so
 * this reads the port back from the server it started rather than hard-coding
 * one. Done in a script instead of a bundler plugin to keep the dependency list
 * to the stack decided in docs/frontend-migration.md.
 */
import { spawn } from "node:child_process";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { build, createServer } from "vite";
import electronBinary from "electron";

const packageRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "..",
);

/**
 * Only the renderer is served by Vite. The main process and the preload script
 * are loaded from `out/` on disk, so they have to be built before Electron
 * starts -- and rebuilt by re-running this script, since neither is hot-reloaded.
 */
async function buildMainAndPreload() {
  const tsc = spawn(
    path.join(packageRoot, "node_modules", ".bin", "tsc"),
    ["-p", "tsconfig.main.json"],
    {
      cwd: packageRoot,
      stdio: "inherit",
      shell: process.platform === "win32",
    },
  );
  const exitCode = await new Promise((resolve) => tsc.on("close", resolve));
  if (exitCode !== 0) {
    throw new Error(`tsc -p tsconfig.main.json exited with ${exitCode}`);
  }
  await build({
    configFile: path.join(packageRoot, "vite.preload.config.mts"),
  });
}

const server = await createServer({ root: packageRoot });
await server.listen();

try {
  await buildMainAndPreload();
} catch (error) {
  await server.close();
  throw error;
}

const url = server.resolvedUrls?.local?.[0];
if (url === undefined) {
  await server.close();
  throw new Error("Vite reported no local URL to point Electron at");
}

// Linux is a development-only platform here (Windows is the product:
// docs/linux-desktop-development.md), and Electron's bundled `chrome-sandbox`
// needs to be root-owned and setuid to start at all. Rather than ask every
// developer to chown a file inside node_modules, the sandbox is dropped on
// Linux only -- never on the platform that ships.
const electronArgs =
  process.platform === "linux" ? [packageRoot, "--no-sandbox"] : [packageRoot];

const child = spawn(electronBinary, electronArgs, {
  cwd: packageRoot,
  stdio: "inherit",
  env: { ...process.env, VITE_DEV_SERVER_URL: url },
});

child.on("close", (code) => {
  void server.close().then(() => process.exit(code ?? 0));
});
