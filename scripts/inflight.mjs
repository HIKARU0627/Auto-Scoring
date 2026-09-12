#!/usr/bin/env node
// Show what every in-flight work in this repository touches, so a worker can
// see a collision *before* starting instead of discovering it at merge time
// (Issue #451). It reads only repository-internal sources:
//
//   * `git worktree list`             -- which branches are checked out where
//   * each worktree's diff against    -- what that worktree actually changes
//     its merge-base with origin/main
//   * the open pull requests' files   -- what already reached a PR, via the
//     GitHub App helper (never `gh`, never personal credentials)
//
// Candidate 1 of Issue #451 exists because this information was only visible to
// the Commander (via scratchpad scripts outside the repository). Workers could
// not answer "is anyone else touching this file / is there already a PR / is my
// base stale?" and five real collisions happened on 2026-09-12.
//
//   node scripts/inflight.mjs              all sources, fetches origin/main first
//   node scripts/inflight.mjs --no-fetch   skip `git fetch origin main`
//   node scripts/inflight.mjs --no-prs     worktrees only; no GitHub call
//   node scripts/inflight.mjs --help
//
// Informational only: exits 0 unless an argument is invalid. The pure decision
// functions are exported so scripts/inflight.test.mjs can pin them with
// `node --test`, the same pattern as scripts/pre-push.test.mjs.
//
// See docs/agent-orchestration.md "着手前チェック" for how a worker uses it.

import { spawnSync } from "node:child_process";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const repoRoot = join(dirname(fileURLToPath(import.meta.url)), "..");
const MAIN_REF = "origin/main";

/** `owner/repo` from an origin remote URL (https or ssh), or null. */
export function parseRepoSlug(url) {
  const match = (url ?? "")
    .trim()
    .match(/github\.com[/:]([^/\s]+)\/([^/\s]+?)(?:\.git)?$/);
  return match === null ? null : `${match[1]}/${match[2]}`;
}

/**
 * `git worktree list --porcelain` is blank-line separated blocks of
 * `key value` lines. Only the first line of a block can be `worktree`; the
 * rest attach to it. A block with no branch is either detached or bare.
 */
export function parseWorktrees(porcelain) {
  const worktrees = [];
  let current = null;
  for (const raw of porcelain.split("\n")) {
    const line = raw.trimEnd();
    if (line === "") {
      if (current !== null) {
        worktrees.push(current);
        current = null;
      }
      continue;
    }
    const space = line.indexOf(" ");
    const key = space === -1 ? line : line.slice(0, space);
    const value = space === -1 ? "" : line.slice(space + 1);
    if (key === "worktree") {
      if (current !== null) worktrees.push(current);
      current = { path: value, branch: null, detached: false };
      continue;
    }
    if (current === null) continue;
    if (key === "branch") {
      current.branch = value.replace(/^refs\/heads\//, "");
    } else if (key === "detached") {
      current.detached = true;
    }
  }
  if (current !== null) worktrees.push(current);
  return worktrees;
}

/**
 * A branch is only ever one of three things here. `merged_at` is checked before
 * `state` because a merged PR is also `state: "closed"`, and the distinction is
 * what keeps a squash-merged worktree (whose branch commits are not ancestors
 * of main) out of the collision report: its files are already in main.
 */
export function pullState(pull) {
  if (pull === null || pull === undefined) return "local";
  if (pull.merged_at !== null && pull.merged_at !== undefined) return "merged";
  if (pull.state === "open") return "open";
  return "closed";
}

/**
 * Files touched by more than one owner. `owners` is `[{ label, files }]`;
 * the "more than one" test is the whole point, so a mutated `> 1` is exactly
 * what the test in inflight.test.mjs pins.
 */
export function collideOwners(owners) {
  const byFile = new Map();
  for (const owner of owners) {
    for (const file of owner.files) {
      if (!byFile.has(file)) byFile.set(file, new Set());
      byFile.get(file).add(owner.label);
    }
  }
  return [...byFile.entries()]
    .filter(([, labels]) => labels.size > 1)
    .map(([file, labels]) => ({ file, owners: [...labels].sort() }))
    .sort((a, b) => a.file.localeCompare(b.file));
}

function branchOf(pull) {
  return pull?.head?.ref ?? null;
}

/**
 * branch -> {number, state}, preferring an open PR over a closed one when a
 * branch was reused. Only open/merged/closed states matter to the caller.
 */
export function indexPulls(pulls) {
  const byBranch = new Map();
  for (const pull of pulls) {
    const branch = branchOf(pull);
    if (branch === null) continue;
    const state = pullState(pull);
    const existing = byBranch.get(branch);
    if (existing === undefined || state === "open") {
      byBranch.set(branch, { number: pull.number, state });
    }
  }
  return byBranch;
}

function branchLabel(worktree) {
  return worktree.branch ?? (worktree.detached ? "(detached)" : "(bare)");
}

function formatCollisions(collisions) {
  if (collisions.length === 0) return "  (none)";
  return collisions
    .map(({ file, owners }) => `  ★ ${file} -> ${owners.join(", ")}`)
    .join("\n");
}

/**
 * Builds the whole report as text. `worktrees` are already-inspected entries
 * (see inspectWorktree); `pullIndex` is indexPulls' output. This is pure so the
 * test can assert the ★ lines without spawning git or pwsh.
 */
export function formatReport({ worktrees, openPulls, pullIndex, warnings }) {
  const lines = [];
  lines.push("== in-flight work ==");
  lines.push("");
  lines.push(
    "Worktrees (files = changed vs origin/main; behind = commits main has):",
  );
  if (worktrees.length === 0) lines.push("  (none)");
  for (const worktree of worktrees) {
    const pull = pullIndex.get(worktree.branch);
    const state =
      pull === undefined ? "local" : `PR #${pull.number} ${pull.state}`;
    const flags = [];
    if (worktree.error !== null) flags.push(`★ ${worktree.error}`);
    if (worktree.behind !== null && worktree.behind > 0) {
      flags.push(
        `★ behind origin/main by ${worktree.behind}; fetch/merge first`,
      );
    }
    if (worktree.dirty !== null && worktree.dirty > 0) {
      flags.push(`${worktree.dirty} uncommitted`);
    }
    lines.push(
      `  ${worktree.name.padEnd(28)} ${branchLabel(worktree).padEnd(36)} ` +
        `files=${worktree.files.length} ahead=${worktree.ahead ?? "?"} ` +
        `behind=${worktree.behind ?? "?"} ${state}` +
        (flags.length > 0 ? `  ${flags.join("; ")}` : ""),
    );
  }
  lines.push("");

  lines.push(`Open pull requests (${openPulls.length}):`);
  if (openPulls.length === 0) lines.push("  (none)");
  for (const pull of openPulls) {
    lines.push(
      `  #${pull.number} ${branchOf(pull) ?? "?"} files=${pull.files.length}`,
    );
  }
  lines.push("");

  const activeOwners = worktrees
    .filter((worktree) => worktree.files.length > 0)
    .filter((worktree) => {
      const pull = pullIndex.get(worktree.branch);
      // A worktree whose PR already merged or closed is stale tree state, not
      // in-flight work; including it is how a leftover worktree would show a
      // collision that cannot happen.
      return pull === undefined || pull.state === "open";
    })
    .map((worktree) => ({
      label: `${worktree.name} (${branchLabel(worktree)})`,
      files: worktree.files,
    }));

  lines.push("Collisions between active worktrees (same file, more than one):");
  lines.push(formatCollisions(collideOwners(activeOwners)));
  lines.push("");

  const prCollisions = collideOwners(
    openPulls.map((pull) => ({
      label: `PR #${pull.number}`,
      files: pull.files,
    })),
  );
  lines.push(
    "Collisions between open pull requests (same file, more than one):",
  );
  lines.push(formatCollisions(prCollisions));

  if (warnings.length > 0) {
    lines.push("");
    lines.push("Warnings:");
    for (const warning of warnings) lines.push(`  ! ${warning}`);
  }
  return lines.join("\n");
}

function runGit(args) {
  const result = spawnSync("git", ["-C", repoRoot, ...args], {
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
  });
  if (result.error !== undefined && result.error !== null) throw result.error;
  if (result.status !== 0) {
    throw new Error(
      `git ${args.join(" ")} exited ${result.status}: ` +
        (result.stderr ?? "").trim(),
    );
  }
  return result.stdout ?? "";
}

/**
 * Everything the report needs about one worktree, with each git call failing
 * independently so one broken worktree does not blank the table. `null` means
 * "could not measure", never a fake zero. `gitInWorktree(args)` is injected so
 * the test does not need a real repository.
 */
export function inspectWorktree(
  worktree,
  gitInWorktree = (args) => runGit(["-C", worktree.path, ...args]),
) {
  const info = {
    name: worktree.path
      .replace(/[/\\]+$/, "")
      .split(/[/\\]/)
      .pop(),
    path: worktree.path,
    branch: worktree.branch,
    detached: worktree.detached,
    files: [],
    ahead: null,
    behind: null,
    dirty: null,
    error: null,
  };

  let base;
  try {
    base = gitInWorktree(["merge-base", MAIN_REF, "HEAD"]).trim();
  } catch (error) {
    info.error = `cannot find merge-base with ${MAIN_REF}: ${error.message}`;
    return info;
  }

  try {
    const changed = gitInWorktree(["diff", "--name-only", base])
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line !== "");
    const untracked = gitInWorktree([
      "ls-files",
      "--others",
      "--exclude-standard",
    ])
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line !== "");
    info.files = [...new Set([...changed, ...untracked])].sort();
  } catch (error) {
    info.error = `cannot list changed files: ${error.message}`;
    return info;
  }

  try {
    info.behind = Number(
      gitInWorktree(["rev-list", "--count", `HEAD..${MAIN_REF}`]).trim(),
    );
    info.ahead = Number(
      gitInWorktree(["rev-list", "--count", `${MAIN_REF}..HEAD`]).trim(),
    );
    info.dirty = gitInWorktree(["status", "--porcelain"])
      .split("\n")
      .filter((line) => line.trim() !== "").length;
  } catch (error) {
    info.error = `cannot measure ahead/behind: ${error.message}`;
  }
  return info;
}

function parseArgs(argv) {
  const options = { fetch: true, noPrs: false, help: false };
  for (let i = 0; i < argv.length; i += 1) {
    const arg = argv[i];
    if (arg === "--no-fetch") options.fetch = false;
    else if (arg === "--no-prs") options.noPrs = true;
    else if (arg === "--help" || arg === "-h") options.help = true;
    else throw new Error(`unknown argument: ${arg}`);
  }
  return options;
}

function spawn(command, args) {
  const result = spawnSync(command, args, {
    cwd: repoRoot,
    encoding: "utf8",
    maxBuffer: 32 * 1024 * 1024,
  });
  if (result.error !== undefined && result.error !== null) throw result.error;
  if (result.status !== 0) {
    throw new Error((result.stderr ?? "").trim() || `exited ${result.status}`);
  }
  return result.stdout ?? "";
}

function remoteSlug() {
  return parseRepoSlug(spawn("git", ["remote", "get-url", "origin"]));
}

/**
 * GitHub App helper call. The helper reads its own credentials and refuses to
 * run outside the repository, so a missing/expired App fails here loudly;
 * runInFlight turns that into a warning and keeps the worktree half.
 */
function api(endpoint) {
  return JSON.parse(
    spawn("pwsh", [
      "-NoProfile",
      "-File",
      join(repoRoot, "scripts", "invoke-github-app-api.ps1"),
      "-Method",
      "Get",
      "-Endpoint",
      endpoint,
    ]),
  );
}

function loadPulls(options, warnings) {
  if (options.noPrs) return { openPulls: [], pullIndex: new Map() };
  const slug = remoteSlug();
  if (slug === null) {
    warnings.push("origin is not a github.com remote; skipping PRs");
    return { openPulls: [], pullIndex: new Map() };
  }
  const pulls = api(`/repos/${slug}/pulls?state=all&per_page=100`);
  const openPulls = [];
  for (const pull of pulls) {
    if (pullState(pull) !== "open") continue;
    const files = api(
      `/repos/${slug}/pulls/${pull.number}/files?per_page=100`,
    ).map((file) => file.filename);
    openPulls.push({ number: pull.number, head: pull.head, files });
  }
  return { openPulls, pullIndex: indexPulls(pulls) };
}

export function runInFlight(options) {
  const warnings = [];
  if (options.fetch) {
    try {
      spawn("git", ["fetch", "origin", "main"]);
    } catch (error) {
      warnings.push(`git fetch origin main failed: ${error.message}`);
    }
  }

  const worktrees = parseWorktrees(runGit(["worktree", "list", "--porcelain"]))
    .filter((worktree) => worktree.branch !== "main")
    .map((worktree) => inspectWorktree(worktree));

  let openPulls = [];
  let pullIndex = new Map();
  try {
    ({ openPulls, pullIndex } = loadPulls(options, warnings));
  } catch (error) {
    warnings.push(`cannot read pull requests: ${error.message}`);
  }

  return {
    report: formatReport({ worktrees, openPulls, pullIndex, warnings }),
    warnings,
  };
}

const HELP = `usage: node scripts/inflight.mjs [--no-fetch] [--no-prs]

Show in-flight worktrees and open PRs, and where they touch the same file.
  --no-fetch   do not run \`git fetch origin main\` first
  --no-prs     skip the GitHub call; worktrees only
`;

function main(argv) {
  let options;
  try {
    options = parseArgs(argv);
  } catch (error) {
    process.stderr.write(`inflight: ${error.message}\n${HELP}`);
    return 2;
  }
  if (options.help) {
    process.stdout.write(HELP);
    return 0;
  }
  process.stdout.write(`${runInFlight(options).report}\n`);
  return 0;
}

const invokedDirectly =
  process.argv[1] !== undefined &&
  import.meta.url === pathToFileURL(process.argv[1]).href;

if (invokedDirectly) {
  process.exitCode = main(process.argv.slice(2));
}
