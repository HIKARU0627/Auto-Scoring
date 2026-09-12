#!/usr/bin/env node
// Scope the pre-push hook to the stacks the pushed diff actually touches
// (Issue #409).
//
// The hook used to run `pnpm lint && pnpm typecheck && pnpm test` for every
// push, so a desktop-only push paid for `flutter test` and `pytest` too. Under
// several workers pushing at once those all ran concurrently outside the
// serialising `heavy-gate.sh` (git starts the hook, so the push cannot be
// wrapped), and one PR that touched no `app/` file was OOM-killed twice by
// `flutter test` inside the hook.
//
// GitHub Actions still runs the full gate set as the required `Quality` check,
// and a hook is bypassable by design (AGENTS.md: "Hooks can be bypassed, so the
// same required checks run in GitHub Actions"). The hook only has to be an
// early, cheap signal, so this script narrows it to the stacks the pushed refs
// touch -- and returns to the full set the moment it cannot prove a change is
// confined to a known stack.
//
//   git push  ->  .githooks/pre-push  ->  `pnpm run check:pre-push`
//             ->  `node scripts/pre-push.mjs` (this file), reading git's stdin
//
// The classification is pure and lives here, not in the shell hook, so
// scripts/pre-push.test.mjs can pin every branch of it with `node --test`
// (the same pattern as scripts/openapi.test.mjs and package-alarm.test.mjs).

import { spawnSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { pathToFileURL } from "node:url";

// A sha of all zeros on the left is a branch deletion; on the right it is a
// branch the remote does not have yet. 40 hex chars for SHA-1 repositories, 64
// for SHA-256, hence a regex instead of a fixed length.
const ZERO_SHA = /^0+$/;

// The only three prefixes that are "known". Anything else -- package.json,
// pnpm-lock.yaml, .github/, scripts/, tsconfig*, a root config, docs/ -- is
// treated as affecting every stack (see classifyPaths): guessing narrow is how
// a hook lets a broken push through.
export const STACK_PREFIXES = Object.freeze({
  app: "app/",
  backend: "backend/",
  desktop: "desktop/",
});

export const STACK_ORDER = Object.freeze(["app", "backend", "desktop"]);

// Phase-major, in the order the old `pnpm lint && pnpm typecheck && pnpm test`
// ran: every lint first (cheapest), then typecheck, then test. `desktop` has no
// lint script -- Prettier covers it repo-wide (docs/quality-gates.md).
export const PHASES = Object.freeze([
  Object.freeze({
    name: "lint",
    tasks: Object.freeze({ app: "lint:app", backend: "lint:backend" }),
  }),
  Object.freeze({
    name: "typecheck",
    tasks: Object.freeze({
      app: "typecheck:app",
      backend: "typecheck:backend",
      desktop: "typecheck:desktop",
    }),
  }),
  Object.freeze({
    name: "test",
    tasks: Object.freeze({
      app: "test:app",
      backend: "test:backend",
      desktop: "test:desktop",
    }),
  }),
]);

/** True for the all-zero local or remote sha git sends for a deletion/new ref. */
export function isZeroSha(sha) {
  return ZERO_SHA.test(sha);
}

/** The remote-side refs this script can diff are branch tips. */
export function isBranchRef(ref) {
  return ref.startsWith("refs/heads/");
}

export function allStacks() {
  return [...STACK_ORDER];
}

/**
 * git hands the pre-push hook one line per pushed ref on stdin:
 *
 *   <local ref> <local sha> <remote ref> <remote sha>
 *
 * Several refs can be pushed at once, so the caller unions their diffs. A line
 * that does not split into four fields throws rather than being ignored; the
 * caller turns that into the full gate set.
 */
export function parsePushLines(text) {
  const pushes = [];
  for (const raw of text.split("\n")) {
    const line = raw.trim();
    if (line === "") continue;
    const fields = line.split(/\s+/);
    if (fields.length !== 4) {
      throw new Error(
        `pre-push: cannot parse stdin line ${JSON.stringify(raw)}`,
      );
    }
    pushes.push({
      localRef: fields[0],
      localSha: fields[1],
      remoteRef: fields[2],
      remoteSha: fields[3],
    });
  }
  return pushes;
}

/**
 * Maps changed repo-relative paths to stacks. A single path outside the three
 * known prefixes (or no recognisable path at all) widens to every stack -- the
 * deliberate "when in doubt, run everything" default.
 */
export function classifyPaths(paths) {
  const stacks = new Set();
  const unknown = [];
  for (const path of paths) {
    const entry = Object.entries(STACK_PREFIXES).find(([, prefix]) =>
      path.startsWith(prefix),
    );
    if (entry === undefined) {
      unknown.push(path);
    } else {
      stacks.add(entry[0]);
    }
  }
  if (unknown.length > 0 || stacks.size === 0) {
    return { all: true, stacks: allStacks(), unknown };
  }
  return {
    all: false,
    stacks: STACK_ORDER.filter((stack) => stacks.has(stack)),
    unknown: [],
  };
}

/** The `pnpm run <task>` names to run, in phase order, for the given stacks. */
export function tasksForStacks(stacks) {
  const selected = new Set(stacks);
  const tasks = [];
  for (const phase of PHASES) {
    for (const stack of STACK_ORDER) {
      if (selected.has(stack) && phase.tasks[stack] !== undefined) {
        tasks.push(phase.tasks[stack]);
      }
    }
  }
  return tasks;
}

function emptyPlan(reason) {
  return {
    all: false,
    stacks: [],
    changedPaths: [],
    reason,
    tasks: [],
  };
}

function allPlan(reason) {
  const stacks = allStacks();
  return {
    all: true,
    stacks,
    changedPaths: [],
    reason,
    tasks: tasksForStacks(stacks),
  };
}

/**
 * Turns git's push lines into the gate plan. `runGit(args)` returns stdout or
 * throws; injecting it keeps every branch testable without a real repository.
 *
 * Per line: a zero local sha is a branch deletion (nothing to inspect); a zero
 * remote sha is a new branch (diff against the merge-base with origin/main);
 * otherwise diff remote..local. Any failure to resolve a diff -- an unknown ref
 * type, a missing origin/main, a git error -- widens to every stack.
 */
export function resolvePlan(pushes, runGit) {
  if (pushes.length === 0) {
    return allPlan("no ref information on stdin (run manually?)");
  }

  const changedPaths = new Set();
  let checkable = false;

  for (const push of pushes) {
    if (isZeroSha(push.localSha)) {
      continue; // Branch deletion: nothing to check.
    }
    if (!isBranchRef(push.localRef)) {
      return allPlan(`pushes non-branch ref ${push.localRef}`);
    }
    checkable = true;

    let base;
    if (isZeroSha(push.remoteSha)) {
      let mergeBase;
      try {
        mergeBase = runGit(["merge-base", "origin/main", push.localSha]).trim();
      } catch (error) {
        return allPlan(
          `cannot find merge-base with origin/main for ${push.localRef}: ` +
            error.message,
        );
      }
      if (mergeBase === "") {
        return allPlan(
          `empty merge-base with origin/main for ${push.localRef}`,
        );
      }
      base = mergeBase;
    } else {
      base = push.remoteSha;
    }

    let output;
    try {
      output = runGit(["diff", "--name-only", base, push.localSha]);
    } catch (error) {
      return allPlan(
        `cannot diff ${base}..${push.localSha} for ${push.localRef}: ` +
          error.message,
      );
    }
    for (const path of output.split("\n")) {
      const trimmed = path.trim();
      if (trimmed !== "") {
        changedPaths.add(trimmed);
      }
    }
  }

  if (!checkable) {
    return emptyPlan("only branch deletions");
  }

  const paths = [...changedPaths].sort();
  if (paths.length === 0) {
    return emptyPlan("no changed paths");
  }

  const classification = classifyPaths(paths);
  if (classification.all) {
    const detail =
      classification.unknown.length > 0
        ? `path(s) outside app/, backend/, desktop/: ` +
          classification.unknown.slice(0, 5).join(", ")
        : "no recognisable stack";
    return {
      ...allPlan(`unknown ${detail}; widening to every stack`),
      changedPaths: paths,
    };
  }

  return {
    all: false,
    stacks: classification.stacks,
    changedPaths: paths,
    reason: `changed under ${classification.stacks.join(", ")}`,
    tasks: tasksForStacks(classification.stacks),
  };
}

function runGit(args) {
  const result = spawnSync("git", args, { encoding: "utf8" });
  if (result.error !== undefined && result.error !== null) {
    throw result.error;
  }
  if (result.status !== 0) {
    throw new Error(`git ${args.join(" ")} exited ${result.status}`);
  }
  return result.stdout ?? "";
}

function readStdin() {
  // A terminal has no push line to read; reading it would block until Ctrl-D.
  if (process.stdin.isTTY === true) {
    return "";
  }
  try {
    return readFileSync(0, "utf8");
  } catch {
    return "";
  }
}

function spawnTask(task) {
  const result = spawnSync("pnpm", ["run", task], { stdio: "inherit" });
  if (result.error !== undefined && result.error !== null) {
    return 1;
  }
  return result.status ?? 1;
}

/**
 * Runs the hook and returns its exit code. Injectable pieces keep the reporting
 * and short-circuit paths testable without spawning git or pnpm.
 */
export function runPrePush(options = {}) {
  const log = options.log ?? console.log;
  const readStdinImpl = options.readStdin ?? readStdin;
  const runGitImpl = options.runGit ?? runGit;
  const runTask = options.runTask ?? spawnTask;

  let pushes;
  try {
    pushes = parsePushLines(readStdinImpl());
  } catch (error) {
    log(`[pre-push] ${error.message}`);
    pushes = null;
  }

  const plan =
    pushes === null
      ? allPlan("unparseable stdin")
      : resolvePlan(pushes, runGitImpl);

  log(`[pre-push] ${plan.reason}`);
  if (plan.changedPaths.length > 0) {
    log(
      `[pre-push] ${plan.changedPaths.length} changed path(s); stack(s): ` +
        `${plan.stacks.join(", ") || "none"}`,
    );
  } else if (plan.all) {
    log("[pre-push] full gate set (safe fallback: cannot scope this push)");
  }

  if (plan.tasks.length === 0) {
    log("[pre-push] nothing to check; skipping gates.");
    return 0;
  }

  log(`[pre-push] ${plan.tasks.map((task) => `pnpm ${task}`).join(" -> ")}`);
  for (const task of plan.tasks) {
    const status = runTask(task);
    if (status !== 0) {
      log(`[pre-push] ${task} failed (exit ${status}); push aborted.`);
      return status;
    }
  }
  return 0;
}

const invokedDirectly =
  process.argv[1] !== undefined &&
  import.meta.url === pathToFileURL(process.argv[1]).href;

if (invokedDirectly) {
  process.exitCode = runPrePush();
}
