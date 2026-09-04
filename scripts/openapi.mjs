// OpenAPI contract tasks. The FastAPI app is the source of truth; the Dart
// client is generated from its schema and committed.
//
//   node scripts/openapi.mjs export     # write backend/openapi/openapi.json
//   node scripts/openapi.mjs generate   # export + regenerate the Dart client
//   node scripts/openapi.mjs check      # generate, then fail on any git diff
//
// `generate` / `check` need `uv`, `dart`, and Java (for openapi-generator) on
// PATH. See docs/sidecar-api.md and docs/quality-gates.md.

import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = join(repoRoot, "backend");
const generatedDir = join(repoRoot, "app", "packages", "auto_scoring_api");
const tracked = ["backend/openapi", "app/packages/auto_scoring_api"];

const isWindows = process.platform === "win32";
const run = (cmd, args, cwd) =>
  execFileSync(cmd, args, { cwd, stdio: "inherit", shell: isWindows });

function exportSchema() {
  run("uv", ["run", "auto-scoring-openapi"], backendDir);
}

function generate() {
  exportSchema();
  run(
    join(repoRoot, "node_modules", ".bin", "openapi-generator-cli"),
    ["generate", "-c", "openapi-generator.yaml"],
    repoRoot,
  );
  run("dart", ["pub", "get"], generatedDir);
  run("dart", ["run", "build_runner", "build"], generatedDir);
  run("dart", ["format", "."], generatedDir);
}

function check() {
  generate();
  const status = execFileSync(
    "git",
    ["status", "--porcelain", "--", ...tracked],
    {
      cwd: repoRoot,
      encoding: "utf8",
      shell: isWindows,
    },
  );
  if (status.trim()) {
    console.error(status);
    console.error(
      "OpenAPI artifacts are stale or untracked. Run `pnpm run openapi:generate` and commit the result.",
    );
    process.exit(1);
  }
}

const task = process.argv[2];
const tasks = { export: exportSchema, generate, check };
if (!tasks[task]) {
  console.error(`usage: node scripts/openapi.mjs <export|generate|check>`);
  process.exit(2);
}
tasks[task]();
