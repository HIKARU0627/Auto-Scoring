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
import {
  cpSync,
  readdirSync,
  readFileSync,
  rmSync,
  renameSync,
  writeFileSync,
} from "node:fs";
import { createRequire } from "node:module";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const backendDir = join(repoRoot, "backend");
const packagesDir = join(repoRoot, "app", "packages");
const generatedDir = join(packagesDir, "auto_scoring_api");
// Scratch/backup directories used to make `generate()` atomic (see below).
// Ignored in app/.gitignore so a leftover one (killed before cleanup) can
// never show up as untracked debris in `git status`.
const scratchPrefix = ".auto_scoring_api.generate-";
const tracked = ["backend/openapi", "app/packages/auto_scoring_api"];
const require = createRequire(import.meta.url);
const generatorCli =
  require.resolve("@openapitools/openapi-generator-cli/main.js");

const run = (cmd, args, cwd) =>
  execFileSync(cmd, args, { cwd, stdio: "inherit" });

function exportSchema() {
  run("uv", ["run", "auto-scoring-openapi"], backendDir);
}

// Remove scratch/backup directories left behind by a run that was killed
// before it could clean up after itself (see `generate()`).
function clearStaleScratchDirs() {
  for (const entry of readdirSync(packagesDir)) {
    if (entry.startsWith(scratchPrefix)) {
      rmSync(join(packagesDir, entry), { recursive: true, force: true });
    }
  }
  rmSync(`${generatedDir}.generate-backup`, {
    recursive: true,
    force: true,
  });
}

// `generate()` used to run openapi-generator, `dart pub get`, `build_runner`,
// and `dart format` directly against the committed `app/packages/
// auto_scoring_api/`, in that order. `dart format` is what turns
// openapi-generator's raw output (trailing whitespace, extra blank lines)
// back into the byte-for-byte formatted form that is committed — so the
// four-step sequence only ever leaves a clean `git status` if it runs to
// completion. Anything that kills the process between openapi-generator and
// `dart format` (a hung `build_runner` being killed by an external timeout,
// an agent process being interrupted, ...) leaves the committed directory
// full of pure-formatting diffs. Reproduced directly: stopping the pipeline
// right after the openapi-generator step left 109 files dirty, all
// whitespace-only (see PR description).
//
// The fix is to never mutate the committed directory until every step has
// already succeeded: run the whole pipeline against a scratch *copy* of it,
// and swap the copy into place with two renames only once `dart format` has
// completed. If anything is killed before that swap, the committed directory
// was never touched and `git status` is exactly as it was before `generate()`
// ran.
//
// The scratch dir is seeded from the current committed directory (not empty)
// because openapi-generator does not overwrite `test/*_test.dart` files that
// already exist, to preserve hand-written test bodies across regenerations.
// Generating into an empty directory defeats that and produces spurious new
// test stubs for any model whose schema has drifted since `test/` was last
// regenerated — a false positive `openapi:check` would not have raised
// against the previous, in-place implementation. Seeding with a copy first
// reproduces exactly the file landscape in-place generation would have seen.
//
// `populate(scratchDir)` runs every mutating step (openapi-generator,
// `dart pub get`, `build_runner`, `dart format`) against the seeded copy.
// `targetDir` is touched only by the two renames at the end, once `populate`
// has returned without throwing — so a throw (a failed step, or the process
// being killed) leaves `targetDir` exactly as it was. Exported so
// `openapi.test.mjs` can exercise the swap itself without the real dart/uv/
// Java toolchain (see that file for the regression test and its mutation
// check).
export function generateIntoScratchThenSwap(targetDir, scratchDir, populate) {
  cpSync(targetDir, scratchDir, { recursive: true });
  try {
    populate(scratchDir);

    const backupDir = `${targetDir}.generate-backup`;
    renameSync(targetDir, backupDir);
    try {
      renameSync(scratchDir, targetDir);
    } catch (error) {
      renameSync(backupDir, targetDir);
      throw error;
    }
    rmSync(backupDir, { recursive: true, force: true });
  } finally {
    rmSync(scratchDir, { recursive: true, force: true });
  }
}

function generate() {
  exportSchema();
  clearStaleScratchDirs();

  const scratchDir = join(packagesDir, `${scratchPrefix}tmp`);
  generateIntoScratchThenSwap(generatedDir, scratchDir, (dir) => {
    run(
      process.execPath,
      [generatorCli, "generate", "-c", "openapi-generator.yaml", "-o", dir],
      repoRoot,
    );
    const manifest = join(dir, ".openapi-generator", "FILES");
    writeFileSync(
      manifest,
      readFileSync(manifest, "utf8").replaceAll("\r\n", "\n"),
    );
    run("dart", ["pub", "get"], dir);
    run("dart", ["run", "build_runner", "build"], dir);
    run("dart", ["format", "."], dir);
  });
}

function check() {
  generate();
  const diff = execFileSync("git", ["diff", "--", ...tracked], {
    cwd: repoRoot,
    encoding: "utf8",
  });
  const untracked = execFileSync(
    "git",
    ["ls-files", "--others", "--exclude-standard", "--", ...tracked],
    { cwd: repoRoot, encoding: "utf8" },
  );
  if (diff.trim() || untracked.trim()) {
    console.error(diff + untracked);
    console.error(
      "OpenAPI artifacts are stale or untracked. Run `pnpm run openapi:generate` and commit the result.",
    );
    process.exit(1);
  }
}

// Guarded so `openapi.test.mjs` can import `generateIntoScratchThenSwap`
// without this file's own CLI dispatch running (and process.exit()-ing the
// test run) as a side effect of the import.
if (import.meta.url === `file://${process.argv[1]}`) {
  const task = process.argv[2];
  const tasks = { export: exportSchema, generate, check };
  if (!tasks[task]) {
    console.error(`usage: node scripts/openapi.mjs <export|generate|check>`);
    process.exit(2);
  }
  tasks[task]();
}
