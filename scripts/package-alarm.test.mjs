#!/usr/bin/env node
// Tests for the Package (Windows) alarm (Issue #312).
//
// The alarm exists to stop a red `Package (Windows)` on `main` from being
// invisible. Its own failure modes have to be caught before that red reaches
// `main`, so this file covers every branch of `scripts/package-alarm.mjs`:
//
//   * the workflow wiring (the job is still named `Package (Windows)`, the
//     alarm still `needs: [package]` and still runs `if: always()`, and
//     `quality` still needs `package`), because a rename, a wrong condition or
//     a dropped dependency would create a monitor that never fires -- or a
//     merge gate that no longer waits for `Package (Windows)` (Issue #331);
//   * the reporting branches (open an issue, comment on one, close it on
//     recovery, go red on a PR, fail closed on an unknown result or a refused
//     API call).
//
//   node --test scripts/package-alarm.test.mjs

import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import * as path from "node:path";
import { test } from "node:test";

import {
  ALARM_JOB_ID,
  PACKAGE_JOB_ID,
  QUALITY_JOB_ID,
  TRACKING_ISSUE_TITLE,
  runPackageAlarm,
  verifyWorkflowWiring,
} from "./package-alarm.mjs";

const HERE = path.dirname(fileURLToPath(import.meta.url));
const CI_YML = readFileSync(
  path.resolve(HERE, "../.github/workflows/ci.yml"),
  "utf8",
);

function jsonResponse(status, body) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  };
}

/** Records every request and lets a test answer (or fail) each one. */
function fakeFetch(handler) {
  const calls = [];
  const fetchImpl = async (url, init = {}) => {
    const call = {
      url,
      method: init.method ?? "GET",
      body: init.body === undefined ? undefined : JSON.parse(init.body),
    };
    calls.push(call);
    return handler(call);
  };
  fetchImpl.calls = calls;
  return fetchImpl;
}

function mainEnv(overrides = {}) {
  return {
    GITHUB_EVENT_NAME: "push",
    GITHUB_REF: "refs/heads/main",
    GITHUB_REPOSITORY: "HIKARU0627/Auto-Scoring",
    GITHUB_RUN_ID: "12345",
    GITHUB_SERVER_URL: "https://github.com",
    GITHUB_SHA: "deadbeef",
    GITHUB_TOKEN: "test-token",
    ...overrides,
  };
}

function prEnv(overrides = {}) {
  return mainEnv({
    GITHUB_EVENT_NAME: "pull_request",
    GITHUB_REF: "refs/pull/42/merge",
    ...overrides,
  });
}

const silent = () => {};

test("the committed ci.yml passes the alarm wiring check", () => {
  assert.deepEqual(verifyWorkflowWiring(CI_YML), []);
});

test("renaming Package (Windows) in ci.yml is caught", () => {
  const renamed = CI_YML.replace(
    /^    name: Package \(Windows\)$/m,
    "    name: Package (Windows) renamed",
  );
  assert.notEqual(renamed, CI_YML, "the fixture rename must have applied");
  assert.match(verifyWorkflowWiring(renamed).join("\n"), /named/);
});

// Synthetic, because `if: always()` also appears on the `quality` job and a
// naive string mutation would edit the wrong job. `package-alarm` is listed
// before `quality` on purpose: the `if: always()` mutation test replaces the
// first occurrence, and it must hit the alarm's.
const HEALTHY_WIRING = [
  "jobs:",
  "  package:",
  "    name: Package (Windows)",
  "    runs-on: windows-latest",
  "  package-alarm:",
  "    needs: [package]",
  "    if: always()",
  "    runs-on: ubuntu-latest",
  "  quality:",
  "    needs: [app, backend, desktop, package]",
  "    if: always()",
].join("\n");

test("the wiring check accepts a healthy job block", () => {
  assert.deepEqual(verifyWorkflowWiring(HEALTHY_WIRING), []);
});

test("a missing package job is caught", () => {
  const without = HEALTHY_WIRING.replace(/  package:\n[\s\S]*?\n/, "");
  assert.match(
    verifyWorkflowWiring(without).join("\n"),
    /has no `package` job/,
  );
});

test("a missing alarm job is caught", () => {
  const without = HEALTHY_WIRING.replace(/  package-alarm:[\s\S]*$/, "");
  assert.match(
    verifyWorkflowWiring(without).join("\n"),
    /has no `package-alarm` job/,
  );
});

test("an alarm that does not need package is caught", () => {
  const without = HEALTHY_WIRING.replace("needs: [package]", "needs: [app]");
  assert.match(
    verifyWorkflowWiring(without).join("\n"),
    /does not need `package`/,
  );
});

test("an alarm without `if: always()` is caught", () => {
  const without = HEALTHY_WIRING.replace("if: always()", "if: success()");
  assert.match(
    verifyWorkflowWiring(without).join("\n"),
    /has no `if: always\(\)`/,
  );
});

test("a quality job that does not need package is caught", () => {
  const without = HEALTHY_WIRING.replace(
    "needs: [app, backend, desktop, package]",
    "needs: [app, backend, desktop]",
  );
  assert.match(
    verifyWorkflowWiring(without).join("\n"),
    new RegExp(`\`${QUALITY_JOB_ID}\` does not need \`${PACKAGE_JOB_ID}\``),
  );
});

test("main failure with no tracking issue opens one", async () => {
  const fetchImpl = fakeFetch((call) => {
    if (
      call.method === "GET" &&
      call.url.endsWith("/issues?state=open&per_page=100")
    ) {
      return jsonResponse(200, []);
    }
    if (call.method === "POST" && call.url.endsWith("/issues")) {
      return jsonResponse(201, { number: 99 });
    }
    throw new Error(`unexpected request: ${call.method} ${call.url}`);
  });

  const code = await runPackageAlarm({
    env: mainEnv({ PACKAGE_RESULT: "failure" }),
    fetchImpl,
    log: silent,
  });

  assert.equal(code, 0);
  assert.deepEqual(
    fetchImpl.calls.map((call) => call.method),
    ["GET", "POST"],
  );
  assert.equal(fetchImpl.calls[1].body.title, TRACKING_ISSUE_TITLE);
  assert.match(fetchImpl.calls[1].body.body, /result: `failure`/);
});

test("main failure with an open tracking issue comments on it", async () => {
  const fetchImpl = fakeFetch((call) => {
    if (call.method === "GET") {
      return jsonResponse(200, [{ number: 7, title: TRACKING_ISSUE_TITLE }]);
    }
    if (call.method === "POST" && call.url.endsWith("/issues/7/comments")) {
      return jsonResponse(201, { id: 1 });
    }
    throw new Error(`unexpected request: ${call.method} ${call.url}`);
  });

  const code = await runPackageAlarm({
    env: mainEnv({ PACKAGE_RESULT: "timed_out" }),
    fetchImpl,
    log: silent,
  });

  assert.equal(code, 0);
  assert.equal(fetchImpl.calls.length, 2);
  assert.match(fetchImpl.calls[1].url, /\/issues\/7\/comments$/);
});

test("main success with an open tracking issue closes it", async () => {
  const fetchImpl = fakeFetch((call) => {
    if (call.method === "GET") {
      return jsonResponse(200, [{ number: 7, title: TRACKING_ISSUE_TITLE }]);
    }
    if (call.method === "POST" && call.url.endsWith("/issues/7/comments")) {
      return jsonResponse(201, { id: 1 });
    }
    if (call.method === "PATCH" && call.url.endsWith("/issues/7")) {
      return jsonResponse(200, { number: 7, state: "closed" });
    }
    throw new Error(`unexpected request: ${call.method} ${call.url}`);
  });

  const code = await runPackageAlarm({
    env: mainEnv({ PACKAGE_RESULT: "success" }),
    fetchImpl,
    log: silent,
  });

  assert.equal(code, 0);
  assert.deepEqual(
    fetchImpl.calls.map((call) => call.method),
    ["GET", "POST", "PATCH"],
  );
  assert.deepEqual(fetchImpl.calls[2].body, {
    state: "closed",
    state_reason: "completed",
  });
});

test("main success with no tracking issue writes nothing", async () => {
  const fetchImpl = fakeFetch((call) => {
    if (call.method === "GET") {
      return jsonResponse(200, []);
    }
    throw new Error(`unexpected request: ${call.method} ${call.url}`);
  });

  const code = await runPackageAlarm({
    env: mainEnv({ PACKAGE_RESULT: "success" }),
    fetchImpl,
    log: silent,
  });

  assert.equal(code, 0);
  assert.deepEqual(
    fetchImpl.calls.map((call) => call.method),
    ["GET"],
  );
});

test("a PR failure turns the alarm job red without touching issues", async () => {
  const lines = [];
  const fetchImpl = fakeFetch((call) => {
    throw new Error(`the alarm must not call the API on a PR: ${call.url}`);
  });

  const code = await runPackageAlarm({
    env: prEnv({ PACKAGE_RESULT: "failure" }),
    fetchImpl,
    log: (line) => lines.push(line),
  });

  assert.equal(code, 1);
  assert.equal(fetchImpl.calls.length, 0);
  assert.match(lines.join("\n"), /::error::Package \(Windows\)/);
});

test("a PR success is a no-op", async () => {
  const fetchImpl = fakeFetch((call) => {
    throw new Error(`the alarm must not call the API on a PR: ${call.url}`);
  });

  const code = await runPackageAlarm({
    env: prEnv({ PACKAGE_RESULT: "success" }),
    fetchImpl,
    log: silent,
  });

  assert.equal(code, 0);
  assert.equal(fetchImpl.calls.length, 0);
});

test("an unknown package result fails closed", async () => {
  await assert.rejects(
    runPackageAlarm({
      env: mainEnv({ PACKAGE_RESULT: "mystery" }),
      fetchImpl: fakeFetch(() => {
        throw new Error("must not be called");
      }),
      log: silent,
    }),
    /unrecognized package result/,
  );
});

test("a refused API call fails the job instead of passing silently", async () => {
  const fetchImpl = fakeFetch(() =>
    jsonResponse(403, { message: "Resource not accessible by integration" }),
  );

  await assert.rejects(
    runPackageAlarm({
      env: mainEnv({ PACKAGE_RESULT: "failure" }),
      fetchImpl,
      log: silent,
    }),
    /failed with 403/,
  );
});

test("a missing token on main fails the job", async () => {
  await assert.rejects(
    runPackageAlarm({
      env: mainEnv({ PACKAGE_RESULT: "failure", GITHUB_TOKEN: undefined }),
      fetchImpl: fakeFetch(() => {
        throw new Error("must not be called");
      }),
      log: silent,
    }),
    /GITHUB_TOKEN are required/,
  );
});
