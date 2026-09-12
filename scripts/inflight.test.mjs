// Pins the decisions scripts/inflight.mjs makes (Issue #451) with `node --test`,
// the same pattern as scripts/openapi.test.mjs and scripts/pre-push.test.mjs.
// Nothing here spawns git or pwsh: the git-facing function takes an injected
// runner, and the report is pure.
//
//   node --test scripts/inflight.test.mjs

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  collideOwners,
  formatReport,
  indexPulls,
  inspectWorktree,
  parseRepoSlug,
  parseWorktrees,
  pullState,
} from "./inflight.mjs";

test("parseRepoSlug reads https and ssh origins and rejects others", () => {
  assert.equal(
    parseRepoSlug("https://github.com/HIKARU0627/Auto-Scoring.git"),
    "HIKARU0627/Auto-Scoring",
  );
  assert.equal(
    parseRepoSlug("git@github.com:HIKARU0627/Auto-Scoring.git"),
    "HIKARU0627/Auto-Scoring",
  );
  assert.equal(
    parseRepoSlug("https://gitlab.com/HIKARU0627/Auto-Scoring.git"),
    null,
  );
});

test("parseWorktrees keeps every block and strips refs/heads/", () => {
  const porcelain = [
    "worktree /repo",
    "HEAD abcdef",
    "branch refs/heads/main",
    "",
    "worktree /repo/.worktrees/issue-451",
    "HEAD 123456",
    "branch refs/heads/HIKARU0627/inflight-451",
    "",
    "worktree /repo/.worktrees/detached",
    "HEAD 999999",
    "detached",
    "",
  ].join("\n");

  const worktrees = parseWorktrees(porcelain);
  assert.equal(worktrees.length, 3);
  assert.deepEqual(worktrees[0], {
    path: "/repo",
    branch: "main",
    detached: false,
  });
  assert.deepEqual(worktrees[1], {
    path: "/repo/.worktrees/issue-451",
    branch: "HIKARU0627/inflight-451",
    detached: false,
  });
  assert.deepEqual(worktrees[2], {
    path: "/repo/.worktrees/detached",
    branch: null,
    detached: true,
  });
});

test("pullState distinguishes merged from merely closed", () => {
  assert.equal(pullState({ state: "open", merged_at: null }), "open");
  assert.equal(
    pullState({ state: "closed", merged_at: "2026-09-12T00:00:00Z" }),
    "merged",
  );
  assert.equal(pullState({ state: "closed", merged_at: null }), "closed");
  assert.equal(pullState(null), "local");
});

test("indexPulls prefers the open PR when a branch was reused", () => {
  const index = indexPulls([
    {
      number: 1,
      state: "closed",
      merged_at: "2026-09-01T00:00:00Z",
      head: { ref: "b" },
    },
    { number: 2, state: "open", merged_at: null, head: { ref: "b" } },
  ]);
  assert.deepEqual(index.get("b"), { number: 2, state: "open" });
});

test("collideOwners reports only files touched by more than one owner", () => {
  const collisions = collideOwners([
    { label: "a", files: ["shared.md", "only-a.ts"] },
    { label: "b", files: ["shared.md", "only-b.ts"] },
    { label: "c", files: ["only-a.ts"] },
  ]);
  assert.deepEqual(collisions, [
    { file: "only-a.ts", owners: ["a", "c"] },
    { file: "shared.md", owners: ["a", "b"] },
  ]);
});

test("collideOwners is empty when every file has a single owner", () => {
  assert.deepEqual(
    collideOwners([
      { label: "a", files: ["a.ts"] },
      { label: "b", files: ["b.ts"] },
    ]),
    [],
  );
});

test("inspectWorktree reads files, ahead/behind and dirty from git", () => {
  const calls = [];
  const fakeGit = (args) => {
    calls.push(args);
    if (args[0] === "merge-base") return "base123\n";
    if (args[0] === "diff") return "a.ts\nb.ts\n";
    if (args[0] === "ls-files") return "c.ts\n";
    if (args[0] === "rev-list" && args[2].startsWith("HEAD..")) return "3\n";
    if (args[0] === "rev-list") return "1\n";
    if (args[0] === "status") return " M a.ts\n";
    throw new Error(`unexpected git ${args.join(" ")}`);
  };
  const info = inspectWorktree(
    { path: "/w/agent-coord-451", branch: "b", detached: false },
    fakeGit,
  );
  assert.deepEqual(info.files, ["a.ts", "b.ts", "c.ts"]);
  assert.equal(info.ahead, 1);
  assert.equal(info.behind, 3);
  assert.equal(info.dirty, 1);
  assert.equal(info.error, null);
  assert.deepEqual(calls[1], ["diff", "--name-only", "base123"]);
});

test("inspectWorktree keeps a failed worktree as an error, not a zero", () => {
  const info = inspectWorktree(
    { path: "/w/broken", branch: "b", detached: false },
    () => {
      throw new Error("boom");
    },
  );
  assert.match(info.error, /boom/);
  assert.equal(info.behind, null);
});

test("formatReport drops merged worktrees from collisions and flags behind", () => {
  const worktrees = [
    {
      name: "live",
      path: "/w/live",
      branch: "live",
      detached: false,
      files: ["shared.md"],
      ahead: 0,
      behind: 2,
      dirty: 0,
      error: null,
    },
    {
      name: "stale",
      path: "/w/stale",
      branch: "stale",
      detached: false,
      files: ["shared.md"],
      ahead: 0,
      behind: 0,
      dirty: 0,
      error: null,
    },
  ];
  const pullIndex = new Map([["stale", { number: 9, state: "merged" }]]);
  const report = formatReport({
    worktrees,
    openPulls: [],
    pullIndex,
    warnings: ["github unavailable"],
  });
  assert.match(report, /★ behind origin\/main by 2/);
  assert.doesNotMatch(report, /★ shared\.md/);
  assert.match(report, /! github unavailable/);
});

test("formatReport marks a live worktree collision", () => {
  const entry = (name, branch, files) => ({
    name,
    path: `/w/${name}`,
    branch,
    detached: false,
    files,
    ahead: 0,
    behind: 0,
    dirty: 0,
    error: null,
  });
  const report = formatReport({
    worktrees: [entry("a", "a", ["shared.md"]), entry("b", "b", ["shared.md"])],
    openPulls: [{ number: 7, head: { ref: "c" }, files: ["shared.md"] }],
    pullIndex: new Map(),
    warnings: [],
  });
  assert.match(report, /★ shared\.md -> a \(a\), b \(b\)/);
  assert.match(report, /#7 c files=1/);
});
