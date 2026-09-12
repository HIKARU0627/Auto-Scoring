#!/usr/bin/env node
// Unit tests for scripts/pre-push.mjs (Issue #409).
//
// The pre-push hook used to run every stack on every push. It now scopes the
// gates to the stacks the pushed diff touches, and the cost of getting that
// classification wrong is asymmetric: a too-narrow result lets a broken push
// through the hook, while a too-wide result only costs time. This file pins
// both directions of every branch -- the push-line parsing, the new/existing/
// deleted ref cases, the "unknown path widens to everything" fallback, and the
// command ordering -- so a silent regression cannot ship.
//
//   node --test scripts/pre-push.test.mjs

import assert from "node:assert/strict";
import { test } from "node:test";

import {
  allStacks,
  classifyPaths,
  isBranchRef,
  isZeroSha,
  parsePushLines,
  resolvePlan,
  runPrePush,
  tasksForStacks,
} from "./pre-push.mjs";

const ZERO = "0".repeat(40);
const A = "a".repeat(40);
const B = "b".repeat(40);
const MERGE_BASE = "c".repeat(40);

/** Records the git arguments and answers (or throws) per call. */
function fakeGit(handler) {
  const calls = [];
  return {
    calls,
    run(args) {
      calls.push(args);
      return handler(args);
    },
  };
}

test("parsePushLines splits git's four fields", () => {
  const pushes = parsePushLines(`refs/heads/feat ${A} refs/heads/feat ${B}\n`);
  assert.deepEqual(pushes, [
    {
      localRef: "refs/heads/feat",
      localSha: A,
      remoteRef: "refs/heads/feat",
      remoteSha: B,
    },
  ]);
});

test("parsePushLines unions several refs and ignores blank lines", () => {
  const pushes = parsePushLines(
    [
      `refs/heads/a ${A} refs/heads/a ${B}`,
      "",
      `refs/heads/b ${B} refs/heads/b ${ZERO}`,
      "",
    ].join("\n"),
  );
  assert.equal(pushes.length, 2);
  assert.equal(pushes[0].localRef, "refs/heads/a");
  assert.equal(pushes[1].localRef, "refs/heads/b");
});

test("parsePushLines throws on a malformed line instead of dropping it", () => {
  assert.throws(
    () => parsePushLines("refs/heads/feat not-a-full-line\n"),
    /cannot parse stdin line/,
  );
});

test("isZeroSha accepts SHA-1 and SHA-256 all-zero shas only", () => {
  assert.equal(isZeroSha(ZERO), true);
  assert.equal(isZeroSha("0".repeat(64)), true);
  assert.equal(isZeroSha(A), false);
  assert.equal(isZeroSha("0000a"), false);
});

test("isBranchRef only accepts branch refs", () => {
  assert.equal(isBranchRef("refs/heads/feat"), true);
  assert.equal(isBranchRef("refs/tags/v1"), false);
  assert.equal(isBranchRef("(delete)"), false);
});

test("classifyPaths scopes a single stack", () => {
  assert.deepEqual(classifyPaths(["backend/x.py"]), {
    all: false,
    stacks: ["backend"],
    unknown: [],
  });
  assert.deepEqual(classifyPaths(["desktop/src/main.ts"]), {
    all: false,
    stacks: ["desktop"],
    unknown: [],
  });
});

test("classifyPaths keeps the canonical stack order across stacks", () => {
  assert.deepEqual(classifyPaths(["desktop/a", "backend/b", "app/c"]).stacks, [
    "app",
    "backend",
    "desktop",
  ]);
});

test("classifyPaths widens to every stack for an unknown path", () => {
  for (const path of [
    "package.json",
    "pnpm-lock.yaml",
    ".github/workflows/ci.yml",
    "scripts/pre-push.mjs",
    "tsconfig.json",
    "docs/quality-gates.md",
    "README.md",
  ]) {
    assert.deepEqual(
      classifyPaths([path]),
      { all: true, stacks: allStacks(), unknown: [path] },
      `${path} must widen to every stack`,
    );
  }
});

test("classifyPaths widens when one path is unknown among known ones", () => {
  const result = classifyPaths(["app/lib/a.dart", "package.json"]);
  assert.equal(result.all, true);
  assert.deepEqual(result.stacks, allStacks());
});

test("tasksForStacks preserves the old phase order", () => {
  assert.deepEqual(tasksForStacks(["app"]), [
    "lint:app",
    "typecheck:app",
    "test:app",
  ]);
  assert.deepEqual(tasksForStacks(["desktop"]), [
    "typecheck:desktop",
    "test:desktop",
  ]);
  assert.deepEqual(tasksForStacks(["app", "backend"]), [
    "lint:app",
    "lint:backend",
    "typecheck:app",
    "typecheck:backend",
    "test:app",
    "test:backend",
  ]);
});

test("the all-stacks plan is exactly the old lint+typecheck+test sequence", () => {
  // The old `check:pre-push` was `pnpm lint && pnpm typecheck && pnpm test`.
  // Widening must not quietly drop a gate.
  assert.deepEqual(tasksForStacks(allStacks()), [
    "lint:app",
    "lint:backend",
    "typecheck:app",
    "typecheck:backend",
    "typecheck:desktop",
    "test:app",
    "test:backend",
    "test:desktop",
  ]);
});

test("resolvePlan runs nothing when every pushed ref is a deletion", () => {
  const git = fakeGit(() => {
    throw new Error("git must not be called for a deletion");
  });
  const plan = resolvePlan(
    [
      {
        localRef: "(delete)",
        localSha: ZERO,
        remoteRef: "refs/heads/feat",
        remoteSha: A,
      },
    ],
    git.run,
  );
  assert.deepEqual(plan.tasks, []);
  assert.equal(plan.all, false);
  assert.deepEqual(git.calls, []);
});

test("resolvePlan diffs remote..local for an existing branch", () => {
  const git = fakeGit((args) => {
    assert.deepEqual(args, ["diff", "--name-only", B, A]);
    return "desktop/src/main.ts\n";
  });
  const plan = resolvePlan(
    [
      {
        localRef: "refs/heads/feat",
        localSha: A,
        remoteRef: "refs/heads/feat",
        remoteSha: B,
      },
    ],
    git.run,
  );
  assert.deepEqual(plan.stacks, ["desktop"]);
  assert.deepEqual(plan.tasks, ["typecheck:desktop", "test:desktop"]);
});

test("resolvePlan uses the origin/main merge-base for a new branch", () => {
  const git = fakeGit((args) => {
    if (args[0] === "merge-base") {
      assert.deepEqual(args, ["merge-base", "origin/main", A]);
      return `${MERGE_BASE}\n`;
    }
    assert.deepEqual(args, ["diff", "--name-only", MERGE_BASE, A]);
    return "app/lib/a.dart\n";
  });
  const plan = resolvePlan(
    [
      {
        localRef: "refs/heads/feat",
        localSha: A,
        remoteRef: "refs/heads/feat",
        remoteSha: ZERO,
      },
    ],
    git.run,
  );
  assert.deepEqual(plan.stacks, ["app"]);
  assert.deepEqual(plan.tasks, ["lint:app", "typecheck:app", "test:app"]);
});

test("resolvePlan unions the changed paths of several refs", () => {
  const git = fakeGit((args) => {
    if (args[0] === "merge-base") {
      return `${MERGE_BASE}\n`;
    }
    if (args[2] === B && args[3] === A) {
      return "app/lib/a.dart\n";
    }
    return "backend/src/x.py\n";
  });
  const plan = resolvePlan(
    [
      {
        localRef: "refs/heads/feat",
        localSha: A,
        remoteRef: "refs/heads/feat",
        remoteSha: B,
      },
      {
        localRef: "refs/heads/other",
        localSha: B,
        remoteRef: "refs/heads/other",
        remoteSha: ZERO,
      },
    ],
    git.run,
  );
  assert.deepEqual(plan.stacks, ["app", "backend"]);
  assert.deepEqual(plan.tasks, [
    "lint:app",
    "lint:backend",
    "typecheck:app",
    "typecheck:backend",
    "test:app",
    "test:backend",
  ]);
});

test("resolvePlan widens to every stack for a non-branch ref", () => {
  const git = fakeGit(() => {
    throw new Error("git must not be called for a tag push");
  });
  const plan = resolvePlan(
    [
      {
        localRef: "refs/tags/v1",
        localSha: A,
        remoteRef: "refs/tags/v1",
        remoteSha: ZERO,
      },
    ],
    git.run,
  );
  assert.equal(plan.all, true);
  assert.deepEqual(plan.tasks, tasksForStacks(allStacks()));
});

test("resolvePlan widens when the merge-base cannot be resolved", () => {
  const git = fakeGit(() => {
    throw new Error("fatal: Not a valid object name origin/main");
  });
  const plan = resolvePlan(
    [
      {
        localRef: "refs/heads/feat",
        localSha: A,
        remoteRef: "refs/heads/feat",
        remoteSha: ZERO,
      },
    ],
    git.run,
  );
  assert.equal(plan.all, true);
});

test("resolvePlan widens when the diff cannot be produced", () => {
  const git = fakeGit(() => {
    throw new Error("fatal: bad object");
  });
  const plan = resolvePlan(
    [
      {
        localRef: "refs/heads/feat",
        localSha: A,
        remoteRef: "refs/heads/feat",
        remoteSha: B,
      },
    ],
    git.run,
  );
  assert.equal(plan.all, true);
});

test("resolvePlan widens when the diff touches an unknown path", () => {
  const git = fakeGit(() => "app/lib/a.dart\n.github/workflows/ci.yml\n");
  const plan = resolvePlan(
    [
      {
        localRef: "refs/heads/feat",
        localSha: A,
        remoteRef: "refs/heads/feat",
        remoteSha: B,
      },
    ],
    git.run,
  );
  assert.equal(plan.all, true);
  assert.deepEqual(plan.tasks, tasksForStacks(allStacks()));
});

test("resolvePlan widens when stdin carried no refs", () => {
  const git = fakeGit(() => {
    throw new Error("git must not be called without refs");
  });
  const plan = resolvePlan([], git.run);
  assert.equal(plan.all, true);
  assert.deepEqual(plan.tasks, tasksForStacks(allStacks()));
});

test("resolvePlan runs nothing when the diff is empty", () => {
  const git = fakeGit(() => "\n");
  const plan = resolvePlan(
    [
      {
        localRef: "refs/heads/feat",
        localSha: A,
        remoteRef: "refs/heads/feat",
        remoteSha: B,
      },
    ],
    git.run,
  );
  assert.deepEqual(plan.tasks, []);
});

test("runPrePush short-circuits on the first failing gate", () => {
  const ran = [];
  const code = runPrePush({
    log: () => {},
    readStdin: () => `refs/heads/feat ${A} refs/heads/feat ${B}\n`,
    runGit: fakeGit(() => "app/lib/a.dart\n").run,
    runTask: (task) => {
      ran.push(task);
      return task === "typecheck:app" ? 3 : 0;
    },
  });
  assert.equal(code, 3);
  assert.deepEqual(ran, ["lint:app", "typecheck:app"]);
});

test("runPrePush falls back to every gate when stdin is unparseable", () => {
  const ran = [];
  const code = runPrePush({
    log: () => {},
    readStdin: () => "not a git push line\n",
    runGit: () => {
      throw new Error("git must not be called for unparseable stdin");
    },
    runTask: (task) => {
      ran.push(task);
      return 0;
    },
  });
  assert.equal(code, 0);
  assert.deepEqual(ran, tasksForStacks(allStacks()));
});

test("runPrePush runs nothing and succeeds for a deletion-only push", () => {
  const ran = [];
  const code = runPrePush({
    log: () => {},
    readStdin: () => `(delete) ${ZERO} refs/heads/feat ${A}\n`,
    runGit: () => {
      throw new Error("git must not be called for a deletion");
    },
    runTask: (task) => {
      ran.push(task);
      return 0;
    },
  });
  assert.equal(code, 0);
  assert.deepEqual(ran, []);
});

test("runPrePush runs only the scoped stack for a backend-only push", () => {
  const ran = [];
  const code = runPrePush({
    log: () => {},
    readStdin: () => `refs/heads/feat ${A} refs/heads/feat ${B}\n`,
    runGit: fakeGit(() => "backend/src/x.py\n").run,
    runTask: (task) => {
      ran.push(task);
      return 0;
    },
  });
  assert.equal(code, 0);
  assert.deepEqual(ran, ["lint:backend", "typecheck:backend", "test:backend"]);
});
