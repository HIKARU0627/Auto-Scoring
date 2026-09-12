#!/usr/bin/env node
// Issue #435: inner-loop "run only what my diff touches" entry points.
//
// This is NOT a gate. `pnpm run check:pre-push` (Issue #409) and the required
// GitHub Actions `Quality` check still own the full run; a per-file selection
// cannot see a test that exercises a change without importing it directly
// (tree-scanning invariant tests, for one). The point here is only to shorten
// the edit -> run loop, so the contract is deliberately visible: the script
// prints every test file it selected, every changed file it could not map, and
// widens to the whole stack the moment it cannot prove a change is confined to
// files it understands.
//
//   pnpm run test:app:changed        # dart test files a local diff can reach
//   pnpm run test:backend:changed    # pytest files a local diff can reach
//   pnpm run test:desktop:changed    # vitest --changed (native module graph)
//
// The diff base defaults to `origin/main` (so branch commits and uncommitted
// edits both count) and can be changed with `--base <ref>`.

import { readdirSync, readFileSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { join } from "node:path";
import { pathToFileURL } from "node:url";

const APP_LIB_PREFIX = "app/lib/";
const BACKEND_SRC_PREFIX = "backend/src/";

/**
 * Per-stack facts. `sourceRef` is the token a test file must contain to count
 * as exercising a changed source file; `null` means the change is outside the
 * stack's source tree (config, assets) and widens to the whole stack.
 */
export const STACK_SPECS = Object.freeze({
  app: {
    name: "app",
    prefix: "app/",
    cwd: "app",
    testPrefix: "app/test/",
    sourceRef(path) {
      if (!path.startsWith(APP_LIB_PREFIX)) return null;
      return `package:auto_scoring_app/${path.slice(APP_LIB_PREFIX.length)}`;
    },
    isTest: (path) =>
      path.startsWith("app/test/") && path.endsWith("_test.dart"),
    runner: (files) => ({ command: "flutter", args: ["test", ...files] }),
  },
  backend: {
    name: "backend",
    prefix: "backend/",
    cwd: "backend",
    testPrefix: "backend/tests/",
    sourceRef(path) {
      if (!path.startsWith(BACKEND_SRC_PREFIX)) return null;
      return path
        .slice(BACKEND_SRC_PREFIX.length)
        .replace(/\.py$/, "")
        .replaceAll("/", ".");
    },
    isTest: (path) =>
      path.startsWith("backend/tests/") &&
      (path.endsWith("_test.py") || /(^|\/)test_[^/]*\.py$/.test(path)),
    runner: (files) => ({ command: "uv", args: ["run", "pytest", ...files] }),
  },
  desktop: {
    name: "desktop",
    prefix: "desktop/",
    cwd: "desktop",
    testPrefix: "desktop/test/",
    // Vitest resolves affected tests from its module graph natively, so no
    // custom sourceRef / isTest are needed here.
    sourceRef: () => null,
    isTest: () => false,
    runner: () => null,
  },
});

const REPO_ROOT = new URL("..", import.meta.url).pathname.replace(/\/$/, "");

/** Test files under the stack's test directory, repo-relative and sorted. */
export function listTestFiles(stack, root, readDirectory = readdirSync) {
  const spec = STACK_SPECS[stack];
  const found = [];
  const walk = (dir) => {
    let entries;
    try {
      entries = readDirectory(dir, { withFileTypes: true });
    } catch {
      return;
    }
    for (const entry of entries) {
      const path = `${dir}/${entry.name}`;
      if (entry.isDirectory()) {
        walk(path);
      } else if (spec.isTest(relativeTo(root, path))) {
        found.push(relativeTo(root, path));
      }
    }
  };
  walk(join(root, spec.testPrefix).replace(/\/$/, ""));
  return found.sort();
}

function relativeTo(root, absolute) {
  return absolute.startsWith(`${root}/`)
    ? absolute.slice(root.length + 1)
    : absolute;
}

/** The stem shared by a source file and its same-named test, or "". */
export function stemOf(path) {
  return path
    .split("/")
    .at(-1)
    .replace(/\.(dart|py|ts|tsx)$/, "")
    .replace(/^test_/, "")
    .replace(/_test$/, "");
}

/**
 * Selects the test files a changed path can reach. Pure: `readFile` and the
 * candidate list are injected so every branch is testable without a repo.
 *
 * A changed test file is always selected. A changed source file selects every
 * candidate whose text mentions its module reference, plus a candidate with the
 * same stem (a barrel/package import would otherwise be missed). A changed file
 * outside the source tree (`sourceRef` returns null) widens to the whole stack.
 */
export function selectTests(stack, changedPaths, testFiles, readFile) {
  const spec = STACK_SPECS[stack];
  const selected = new Set();
  const unmapped = [];
  let widen = false;

  for (const path of changedPaths) {
    if (!path.startsWith(spec.prefix)) continue;
    if (spec.isTest(path)) {
      selected.add(path);
      continue;
    }
    const ref = spec.sourceRef(path);
    if (ref === null) {
      widen = true;
      continue;
    }
    const stem = stemOf(path);
    const matches = testFiles.filter(
      (test) => readFile(test).includes(ref) || stemOf(test) === stem,
    );
    if (matches.length === 0) {
      unmapped.push(path);
    } else {
      for (const test of matches) selected.add(test);
    }
  }

  return { stack, selected: [...selected].sort(), unmapped, widen };
}

/** The plan for every stack the diff touches, plus stacks it does not. */
export function buildPlan(changedPaths, testFilesByStack, readFile) {
  const plans = [];
  for (const stack of Object.keys(STACK_SPECS)) {
    if (
      !changedPaths.some((path) => path.startsWith(STACK_SPECS[stack].prefix))
    ) {
      continue;
    }
    const plan = selectTests(
      stack,
      changedPaths,
      testFilesByStack[stack],
      readFile,
    );
    if (stack === "desktop") {
      plan.selected = testFilesByStack[stack];
      plan.mode = "vitest-changed";
    } else if (plan.widen) {
      plan.selected = testFilesByStack[stack];
      plan.mode = "whole-stack";
    } else {
      plan.mode = "selected";
    }
    plans.push(plan);
  }
  return plans;
}

function runGit(args) {
  const result = spawnSync("git", args, { cwd: REPO_ROOT, encoding: "utf8" });
  if (result.error !== undefined && result.error !== null) throw result.error;
  if (result.status !== 0) {
    throw new Error(`git ${args.join(" ")} exited ${result.status}`);
  }
  return result.stdout ?? "";
}

/** Working tree + branch commits vs `base`, including untracked files. */
export function changedPaths(base, git = runGit) {
  const tracked = git(["diff", "--name-only", base])
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
  const untracked = git(["ls-files", "--others", "--exclude-standard"])
    .split("\n")
    .map((line) => line.trim())
    .filter((line) => line !== "");
  return [...new Set([...tracked, ...untracked])].sort();
}

function parseArgs(argv) {
  const stack = argv[0];
  let base = "origin/main";
  let dryRun = false;
  for (let i = 1; i < argv.length; i += 1) {
    if (argv[i] === "--base" && argv[i + 1] !== undefined) {
      base = argv[i + 1];
      i += 1;
    } else if (argv[i].startsWith("--base=")) {
      base = argv[i].slice("--base=".length);
    } else if (argv[i] === "--dry-run") {
      dryRun = true;
    }
  }
  return { stack, base, dryRun };
}

/** Repo-relative selection -> paths the stack runner (run from its cwd) sees. */
export function relativeToStack(stack, paths) {
  const { prefix } = STACK_SPECS[stack];
  return paths.map((path) =>
    path.startsWith(prefix) ? path.slice(prefix.length) : path,
  );
}

/** The command a stack's runner will be spawned with, for logging/dry-run. */
export function runnerCommand(stack, plan, base) {
  if (stack === "desktop") {
    // Vitest owns the module graph; hand it the same diff base the other
    // stacks use so all three answer "what did my whole diff touch?".
    return {
      command: "pnpm",
      args: ["exec", "vitest", "run", `--changed=${base}`],
      cwd: join(REPO_ROOT, "desktop"),
    };
  }
  // The runners execute from the stack directory, so the repo-relative
  // selection has to lose its stack prefix before it is handed over.
  const relative = relativeToStack(stack, plan.selected);
  const { command, args } = STACK_SPECS[stack].runner(relative);
  return { command, args, cwd: join(REPO_ROOT, STACK_SPECS[stack].cwd) };
}

function spawnRunner(stack, plan, base) {
  if (plan.selected.length === 0 && stack !== "desktop") {
    console.log(`[changed] ${stack}: no tests selected; nothing to run.`);
    return { status: 0 };
  }
  const { command, args, cwd } = runnerCommand(stack, plan, base);
  return spawnSync(command, args, { cwd, stdio: "inherit" });
}

export function run(argv = process.argv.slice(2), deps = {}) {
  const { stack, base, dryRun } = parseArgs(argv);
  if (!(stack in STACK_SPECS)) {
    console.error(
      `usage: changed-tests.mjs <${Object.keys(STACK_SPECS).join("|")}> [--base <ref>]`,
    );
    return 2;
  }

  const git = deps.git ?? runGit;
  const readFile =
    deps.readFile ?? ((path) => readFileSync(join(REPO_ROOT, path), "utf8"));
  const readDirectory = deps.readDirectory ?? readdirSync;
  const spawn = deps.spawn ?? spawnRunner;

  let paths;
  try {
    paths = changedPaths(base, git);
  } catch (error) {
    console.error(`[changed] cannot diff against ${base}: ${error.message}`);
    return 1;
  }

  const testFilesByStack = {};
  for (const name of Object.keys(STACK_SPECS)) {
    testFilesByStack[name] = listTestFiles(name, REPO_ROOT, readDirectory);
  }

  const plan = buildPlan(paths, testFilesByStack, readFile).find(
    (entry) => entry.stack === stack,
  );
  if (plan === undefined) {
    console.log(`[changed] ${stack}: no ${base} diff touches this stack.`);
    return 0;
  }

  if (plan.unmapped.length > 0) {
    console.log(
      `[changed] ${stack}: ${plan.unmapped.length} changed file(s) with no ` +
        `directly-importing test (not run): ${plan.unmapped.join(", ")}`,
    );
  }
  if (plan.mode === "whole-stack") {
    console.log(
      `[changed] ${stack}: a change outside the source tree widens to the whole stack.`,
    );
  } else if (plan.mode === "vitest-changed") {
    console.log(`[changed] ${stack}: vitest --changed=${base}`);
  } else {
    console.log(
      `[changed] ${stack}: ${plan.selected.length} test file(s): ${plan.selected.join(", ")}`,
    );
  }

  if (dryRun) {
    const { command, args, cwd } = runnerCommand(stack, plan, base);
    console.log(
      `[changed] would run: (cd ${relativeTo(REPO_ROOT, cwd)} && ` +
        `${command} ${args.join(" ")})`,
    );
    return 0;
  }

  const result = spawn(stack, plan, base);
  if (result.error !== undefined && result.error !== null) {
    console.error(`[changed] ${stack}: ${result.error.message}`);
    return 1;
  }
  return result.status ?? 1;
}

const invokedDirectly =
  process.argv[1] !== undefined &&
  import.meta.url === pathToFileURL(process.argv[1]).href;

if (invokedDirectly) {
  process.exitCode = run();
}
