// TypeScript OpenAPI client generation for desktop/.
//
//   node scripts/openapi-ts.mjs generate   # regenerate desktop/src/renderer/api/generated
//   node scripts/openapi-ts.mjs check      # generate, then fail on any git diff
//
// Reads the committed schema only (`backend/openapi/openapi.json`). Does not
// export from FastAPI and does not touch the Dart client (`scripts/openapi.mjs`).
// Generation is atomic via `generateIntoScratchThenSwap` (Issue #102).

import { execFileSync } from "node:child_process";
import {
  cpSync,
  existsSync,
  mkdirSync,
  readdirSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { generateIntoScratchThenSwap } from "./openapi.mjs";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const desktopDir = join(repoRoot, "desktop");
const generatedDir = join(desktopDir, "src", "renderer", "api", "generated");
const scratchPrefix = ".api-generated-";
const inputSchema = join(repoRoot, "backend", "openapi", "openapi.json");
const tracked = ["desktop/src/renderer/api/generated"];
const openapiTypescriptCli = join(
  repoRoot,
  "node_modules",
  "openapi-typescript",
  "bin",
  "cli.js",
);

const run = (cmd, args, cwd) =>
  execFileSync(cmd, args, { cwd, stdio: "inherit" });

function clearStaleScratchDirs() {
  const apiDir = join(desktopDir, "src", "renderer", "api");
  for (const entry of readdirSync(apiDir)) {
    if (entry.startsWith(scratchPrefix)) {
      rmSync(join(apiDir, entry), { recursive: true, force: true });
    }
  }
  rmSync(`${generatedDir}.generate-backup`, {
    recursive: true,
    force: true,
  });
}

function ensureGeneratedDirExists() {
  if (!existsSync(generatedDir)) {
    mkdirSync(generatedDir, { recursive: true });
    writeFileSync(
      join(generatedDir, ".gitkeep"),
      "# Placeholder until the first `pnpm run openapi:generate:ts`.\n",
    );
  }
}

function generate() {
  clearStaleScratchDirs();
  ensureGeneratedDirExists();

  const scratchDir = join(
    desktopDir,
    "src",
    "renderer",
    "api",
    `${scratchPrefix}tmp`,
  );
  generateIntoScratchThenSwap(generatedDir, scratchDir, (dir) => {
    const schemaPath = join(dir, "schema.ts");
    run(
      process.execPath,
      [openapiTypescriptCli, inputSchema, "-o", schemaPath],
      repoRoot,
    );
    // openapi-typescript output is not Prettier-formatted; running Prettier here
    // (like `dart format` in scripts/openapi.mjs) keeps `openapi:check:ts` from
    // failing on whitespace-only drift after a regenerate.
    run(
      process.execPath,
      [
        join(repoRoot, "node_modules", "prettier", "bin", "prettier.cjs"),
        "--write",
        schemaPath,
      ],
      repoRoot,
    );
    writeFileSync(
      join(dir, "README.md"),
      [
        "# Generated OpenAPI types",
        "",
        "Do not edit by hand. Regenerate with `pnpm run openapi:generate:ts`.",
        "",
      ].join("\n"),
    );
    rmSync(join(dir, ".gitkeep"), { force: true });
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
      "TypeScript OpenAPI artifacts are stale or untracked. Run `pnpm run openapi:generate:ts` and commit the result.",
    );
    process.exit(1);
  }
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const task = process.argv[2];
  const tasks = { generate, check };
  if (!tasks[task]) {
    console.error(`usage: node scripts/openapi-ts.mjs <generate|check>`);
    process.exit(2);
  }
  tasks[task]();
}
