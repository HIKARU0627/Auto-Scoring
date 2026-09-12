import { test } from "node:test";
import assert from "node:assert/strict";

import {
  STACK_SPECS,
  changedPaths,
  listTestFiles,
  relativeToStack,
  runnerCommand,
  selectTests,
  stemOf,
  buildPlan,
} from "./changed-tests.mjs";

const read = (contents) => () => contents;

test("app: a changed lib file selects every test that imports it", () => {
  const plan = selectTests(
    "app",
    ["app/lib/features/pdf_review/pdf_review_page.dart"],
    ["app/test/pdf_review_page_test.dart", "app/test/home_page_test.dart"],
    (path) =>
      path.endsWith("pdf_review_page_test.dart")
        ? "import 'package:auto_scoring_app/features/pdf_review/pdf_review_page.dart';"
        : "import 'package:auto_scoring_app/features/home/home_page.dart';",
  );
  assert.deepEqual(plan.selected, ["app/test/pdf_review_page_test.dart"]);
  assert.equal(plan.widen, false);
  assert.deepEqual(plan.unmapped, []);
});

test("app: a changed test file is selected directly", () => {
  const plan = selectTests(
    "app",
    ["app/test/home_page_test.dart"],
    ["app/test/home_page_test.dart"],
    read(""),
  );
  assert.deepEqual(plan.selected, ["app/test/home_page_test.dart"]);
});

test("app: a file outside lib/ widens to the whole stack", () => {
  const plan = selectTests(
    "app",
    ["app/pubspec.yaml"],
    ["app/test/a_test.dart"],
    read(""),
  );
  assert.equal(plan.widen, true);
  assert.deepEqual(plan.selected, []);
});

test("app: a source file no test names is reported as unmapped, not dropped silently", () => {
  const plan = selectTests(
    "app",
    ["app/lib/features/orphan/orphan_page.dart"],
    ["app/test/home_page_test.dart"],
    (path) =>
      path.endsWith("orphan")
        ? "package:auto_scoring_app/features/orphan/orphan_page.dart"
        : "home",
  );
  assert.deepEqual(plan.unmapped, ["app/lib/features/orphan/orphan_page.dart"]);
  assert.deepEqual(plan.selected, []);
});

test("backend: a changed module selects the tests importing its dotted path", () => {
  const plan = selectTests(
    "backend",
    ["backend/src/auto_scoring/domain/answer_area.py"],
    ["backend/tests/test_answer_area_api.py", "backend/tests/test_home.py"],
    (path) =>
      path.endsWith("test_answer_area_api.py")
        ? "from auto_scoring.domain.answer_area import AnswerArea"
        : "from auto_scoring.domain.models import Question",
  );
  assert.deepEqual(plan.selected, ["backend/tests/test_answer_area_api.py"]);
});

test("backend: same-stem test is selected even without a matching import", () => {
  const plan = selectTests(
    "backend",
    ["backend/src/auto_scoring/domain/answer_area_detection.py"],
    ["backend/tests/test_answer_area_detection.py"],
    read(""),
  );
  assert.deepEqual(plan.selected, [
    "backend/tests/test_answer_area_detection.py",
  ]);
});

test("stemOf strips the test affixes", () => {
  assert.equal(
    stemOf("backend/tests/test_answer_area_detection.py"),
    "answer_area_detection",
  );
  assert.equal(stemOf("app/test/home_page_test.dart"), "home_page");
  assert.equal(stemOf("app/lib/features/home/home_page.dart"), "home_page");
});

test("desktop uses vitest --changed rather than selecting files itself", () => {
  const plan = buildPlan(
    ["desktop/src/renderer/AppShell.tsx"],
    { app: [], backend: [], desktop: ["desktop/test/renderer/app.test.tsx"] },
    read(""),
  ).find((entry) => entry.stack === "desktop");
  assert.equal(plan.mode, "vitest-changed");
});

test("buildPlan only mentions stacks the diff touches", () => {
  const plans = buildPlan(
    ["app/lib/foo.dart"],
    { app: ["app/test/foo_test.dart"], backend: [], desktop: [] },
    read(""),
  );
  assert.deepEqual(
    plans.map((plan) => plan.stack),
    ["app"],
  );
});

test("changedPaths unions tracked and untracked, deduped and sorted", () => {
  const paths = changedPaths("origin/main", (args) => {
    if (args[0] === "diff") return "b.txt\na.txt\n";
    return "a.txt\nc.txt\n";
  });
  assert.deepEqual(paths, ["a.txt", "b.txt", "c.txt"]);
});

test("listTestFiles keeps only the stack's test-file pattern", () => {
  const entries = {
    "/root/app/test": [
      { name: "home_page_test.dart", isDirectory: () => false },
      { name: "fixtures", isDirectory: () => true },
      { name: "helper.dart", isDirectory: () => false },
    ],
    "/root/app/test/fixtures": [
      { name: "sample_test.dart", isDirectory: () => false },
    ],
  };
  const readDirectory = (dir) => entries[dir] ?? [];
  assert.deepEqual(listTestFiles("app", "/root", readDirectory), [
    "app/test/fixtures/sample_test.dart",
    "app/test/home_page_test.dart",
  ]);
});

test("relativeToStack strips the stack prefix the runner does not expect", () => {
  assert.deepEqual(relativeToStack("app", ["app/test/home_page_test.dart"]), [
    "test/home_page_test.dart",
  ]);
  assert.deepEqual(relativeToStack("backend", ["backend/tests/test_api.py"]), [
    "tests/test_api.py",
  ]);
});

test("runnerCommand hands the stack runner paths relative to its cwd", () => {
  const app = runnerCommand(
    "app",
    { selected: ["app/test/home_page_test.dart"] },
    "origin/main",
  );
  assert.equal(app.command, "flutter");
  assert.deepEqual(app.args, ["test", "test/home_page_test.dart"]);
  assert.ok(app.cwd.endsWith("/app"));

  const desktop = runnerCommand("desktop", { selected: [] }, "origin/main");
  assert.deepEqual(desktop.args, [
    "exec",
    "vitest",
    "run",
    "--changed=origin/main",
  ]);
});

test("backend: a small selection opts out of the parallel addopts with -n0", () => {
  const backend = runnerCommand(
    "backend",
    { selected: ["backend/tests/test_a.py", "backend/tests/test_b.py"] },
    "origin/main",
  );
  assert.equal(backend.command, "uv");
  assert.deepEqual(backend.args, [
    "run",
    "pytest",
    "-n0",
    "tests/test_a.py",
    "tests/test_b.py",
  ]);
});

test("backend: only a small selection is serial, not a large one", () => {
  const selection = (count) => ({
    selected: Array.from(
      { length: count },
      (_, i) => `backend/tests/test_${i}.py`,
    ),
  });
  assert.ok(
    runnerCommand("backend", selection(7), "origin/main").args.includes("-n0"),
  );
  assert.ok(
    !runnerCommand("backend", selection(8), "origin/main").args.includes("-n0"),
  );
});

test("every stack has the same script-facing shape", () => {
  for (const spec of Object.values(STACK_SPECS)) {
    assert.equal(typeof spec.sourceRef, "function");
    assert.equal(typeof spec.isTest, "function");
    assert.ok(spec.testPrefix.endsWith("/"));
  }
});
