// Regression test for Issue #102: `openapi:generate` must never leave the
// committed `app/packages/auto_scoring_api/` dirty just because it was
// interrupted mid-run (a hung `build_runner` killed by an external timeout,
// an agent process being killed, ...). See scripts/openapi.mjs for the fix
// (generate into a scratch copy, swap it in only once every step succeeded).
//
// This test exercises `generateIntoScratchThenSwap` directly with fake,
// instant "steps" instead of the real dart/uv/Java toolchain, so it runs in
// milliseconds and needs nothing beyond Node itself.
//
//   node --test scripts/openapi.test.mjs

import assert from "node:assert/strict";
import {
  mkdtempSync,
  mkdirSync,
  readFileSync,
  rmSync,
  writeFileSync,
} from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { test } from "node:test";

import { generateIntoScratchThenSwap } from "./openapi.mjs";

test("committed dir gets the new content once every step succeeds", () => {
  const root = mkdtempSync(join(tmpdir(), "openapi-atomic-"));
  const targetDir = join(root, "committed");
  const scratchDir = join(root, "scratch");
  mkdirSync(targetDir);
  writeFileSync(join(targetDir, "api.dart"), "old\n");

  try {
    generateIntoScratchThenSwap(targetDir, scratchDir, (dir) => {
      writeFileSync(join(dir, "api.dart"), "new\n");
    });

    assert.equal(readFileSync(join(targetDir, "api.dart"), "utf8"), "new\n");
    assert.throws(() => readFileSync(scratchDir), /ENOENT/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});

// The property under test is the one Issue #102 is about: a failure between
// openapi-generator writing raw output and `dart format` cleaning it up must
// not dirty the committed directory. Mutate `generateIntoScratchThenSwap` to
// swap in the scratch dir *before* running `populate` (i.e. reintroduce the
// non-atomic in-place pipeline) and this test fails, because `targetDir`
// then does carry the half-finished "new" content instead of "old".
test("a step throwing before the swap leaves the committed dir untouched", () => {
  const root = mkdtempSync(join(tmpdir(), "openapi-atomic-"));
  const targetDir = join(root, "committed");
  const scratchDir = join(root, "scratch");
  mkdirSync(targetDir);
  writeFileSync(join(targetDir, "api.dart"), "old\n");
  const before = readFileSync(join(targetDir, "api.dart"), "utf8");

  try {
    assert.throws(() => {
      generateIntoScratchThenSwap(targetDir, scratchDir, (dir) => {
        // Simulates openapi-generator having already written its raw,
        // unformatted output into the scratch copy...
        writeFileSync(join(dir, "api.dart"), "new-but-unformatted\n");
        // ...before the step that would have finished the pipeline (here:
        // `dart format`) gets killed.
        throw new Error("simulated kill mid-pipeline");
      });
    }, /simulated kill mid-pipeline/);

    assert.equal(readFileSync(join(targetDir, "api.dart"), "utf8"), before);
    assert.throws(() => readFileSync(scratchDir), /ENOENT/);
  } finally {
    rmSync(root, { recursive: true, force: true });
  }
});
