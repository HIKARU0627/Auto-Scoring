#!/usr/bin/env node
// Package (Windows) alarm -- Issue #312.
//
// `Quality` is the only status check the `main` ruleset requires. Issue #331
// (owner ruling, 2026-09-12) added `package` to `Quality`'s `needs`, so on a
// pull request a red `Package (Windows)` now blocks the merge itself. This
// alarm covers what a required check cannot: a change that reaches `main`
// without a pull request (an owner or admin push, a ruleset exception, a later
// configuration change). There is no required check to run there and nobody is
// forced to open the run.
//
// That matters because Windows is the only place the shipped Windows artifacts
// can be built or verified: PyInstaller cannot cross-compile, and
// `pnpm run build:app` (`flutter build windows`) cannot run on Linux. When
// `Package (Windows)` is red on `main`, the only signal that the Windows build
// broke is that red job. This script turns it into something a person will see:
//
//   * a push to `main` opens (or comments on) a tracking issue, and closes it
//     again once the job is green;
//   * everywhere else it makes the alarm job itself red, so the same detection
//     can be mutation-tested from a pull request before it ever reaches `main`.
//
// The job that runs this is `package-alarm` in `.github/workflows/ci.yml`. It
// is deliberately not in `Quality`'s `needs`: it is a monitor, not a gate. The
// wiring self-test below (`verifyWorkflowWiring`) also asserts that `quality`
// still needs `package`, so a change that silently drops Issue #331's
// required-check wiring turns `pnpm run alarm:selftest` red.

import { pathToFileURL } from "node:url";

export const PACKAGE_JOB_ID = "package";
export const PACKAGE_JOB_NAME = "Package (Windows)";
export const ALARM_JOB_ID = "package-alarm";
// Issue #331 folds `package` into this job's verdict; the self-test below
// guards that wiring.
export const QUALITY_JOB_ID = "quality";
export const TRACKING_ISSUE_TITLE = `main: ${PACKAGE_JOB_NAME} is failing`;

// Every job result GitHub can report for `package`. Anything else means the
// workflow no longer matches what this script expects, and the script fails
// instead of passing silently.
export const KNOWN_JOB_RESULTS = Object.freeze([
  "success",
  "failure",
  "cancelled",
  "timed_out",
  "skipped",
]);

const DEFAULT_API_BASE = "https://api.github.com";

/** True only for the `main` push this alarm is allowed to open issues for. */
export function isMainPush(env) {
  return (
    env.GITHUB_EVENT_NAME === "push" && env.GITHUB_REF === "refs/heads/main"
  );
}

/**
 * One authenticated GitHub REST call. Throws on any non-2xx response -- a
 * missing `issues: write` permission or a bad token must surface as a red job,
 * not as a silent no-op.
 */
export async function githubRequest(fetchImpl, token, method, url, body) {
  const response = await fetchImpl(url, {
    method,
    headers: {
      Authorization: `Bearer ${token}`,
      Accept: "application/vnd.github+json",
      "X-GitHub-Api-Version": "2022-11-28",
      "User-Agent": "auto-scoring-package-alarm",
      ...(body === undefined ? {} : { "Content-Type": "application/json" }),
    },
    ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
  if (!response.ok) {
    throw new Error(
      `package-alarm: GitHub API ${method} ${url} failed with ` +
        `${response.status}: ${await response.text()}`,
    );
  }
  if (response.status === 204) {
    return null;
  }
  return response.json();
}

async function findOpenTrackingIssue({ fetchImpl, token, repo, apiBase }) {
  const issues = await githubRequest(
    fetchImpl,
    token,
    "GET",
    `${apiBase}/repos/${repo}/issues?state=open&per_page=100`,
  );
  return (
    issues.find(
      (issue) =>
        issue.pull_request === undefined &&
        issue.title === TRACKING_ISSUE_TITLE,
    ) ?? null
  );
}

function failureBody({ result, ref, sha, runUrl }) {
  return [
    `\`${PACKAGE_JOB_NAME}\` did not succeed on \`main\`.`,
    "",
    `- result: \`${result}\``,
    `- ref: \`${ref}\``,
    `- commit: \`${sha}\``,
    `- run: ${runUrl}`,
    "",
    "Windows is the only environment where the shipped Windows artifacts can " +
      "be built (PyInstaller cannot cross-compile and `pnpm run build:app` " +
      "cannot run on Linux), so this red is the only signal that the Windows " +
      "build may be broken.",
    "",
    "Opened by the `package-alarm` job. It closes automatically once " +
      `\`${PACKAGE_JOB_NAME}\` succeeds on \`main\` again.`,
  ].join("\n");
}

/**
 * Runs the alarm and returns the process exit code, or throws when the wiring
 * itself is broken (unknown job result, missing token, API failure). A thrown
 * error is the "the monitor turned red" path.
 */
export async function runPackageAlarm(options = {}) {
  const env = options.env ?? process.env;
  const fetchImpl = options.fetchImpl ?? globalThis.fetch;
  const log = options.log ?? console.log;
  const apiBase = options.apiBase ?? env.GITHUB_API_URL ?? DEFAULT_API_BASE;

  const result = env.PACKAGE_RESULT;
  const repository = env.GITHUB_REPOSITORY;
  const token = env.GITHUB_TOKEN;
  const ref = env.GITHUB_REF;
  const serverUrl = env.GITHUB_SERVER_URL ?? "https://github.com";
  const runUrl = `${serverUrl}/${repository}/actions/runs/${env.GITHUB_RUN_ID}`;

  if (!KNOWN_JOB_RESULTS.includes(result)) {
    throw new Error(
      `package-alarm: unrecognized ${PACKAGE_JOB_ID} result ` +
        `${JSON.stringify(result)}; refusing to pass silently`,
    );
  }

  if (!isMainPush(env)) {
    if (result === "success") {
      log(
        `package-alarm: ${PACKAGE_JOB_NAME} succeeded on ${ref}; the alarm ` +
          "only files issues for `main`.",
      );
      return 0;
    }
    log(
      `::error::${PACKAGE_JOB_NAME} did not succeed (result=${result}) on ` +
        `${ref}. The Windows artifacts could not be verified. Run: ${runUrl}`,
    );
    return 1;
  }

  if (repository === undefined || token === undefined) {
    throw new Error(
      "package-alarm: GITHUB_REPOSITORY and GITHUB_TOKEN are required to " +
        "report on `main`",
    );
  }

  const existing = await findOpenTrackingIssue({
    fetchImpl,
    token,
    repo: repository,
    apiBase,
  });

  if (result === "success") {
    if (existing === null) {
      log(
        `package-alarm: ${PACKAGE_JOB_NAME} is green and no tracking issue ` +
          "is open.",
      );
      return 0;
    }
    await githubRequest(
      fetchImpl,
      token,
      "POST",
      `${apiBase}/repos/${repository}/issues/${existing.number}/comments`,
      {
        body:
          `${PACKAGE_JOB_NAME} succeeded again on \`main\` at ` +
          `${env.GITHUB_SHA}. Closing this alarm.\n\n${runUrl}`,
      },
    );
    await githubRequest(
      fetchImpl,
      token,
      "PATCH",
      `${apiBase}/repos/${repository}/issues/${existing.number}`,
      { state: "closed", state_reason: "completed" },
    );
    log(`package-alarm: closed tracking issue #${existing.number}.`);
    return 0;
  }

  const body = failureBody({ result, ref, sha: env.GITHUB_SHA, runUrl });
  if (existing !== null) {
    await githubRequest(
      fetchImpl,
      token,
      "POST",
      `${apiBase}/repos/${repository}/issues/${existing.number}/comments`,
      { body },
    );
    log(`package-alarm: commented on tracking issue #${existing.number}.`);
    return 0;
  }
  const created = await githubRequest(
    fetchImpl,
    token,
    "POST",
    `${apiBase}/repos/${repository}/issues`,
    { title: TRACKING_ISSUE_TITLE, body },
  );
  log(`package-alarm: opened tracking issue #${created.number}.`);
  return 0;
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

/**
 * Line-based reader for the indented job block of `jobId` under `jobs:`.
 * Returns `null` when the job is absent. It does not need a YAML parser: the
 * checks below only look at four-space `name:` / `needs:` / `if:` keys, and a
 * real parser would be a dependency this gate does not otherwise need.
 */
export function jobBlock(ciYaml, jobId) {
  const lines = ciYaml.split("\n");
  const jobsIndex = lines.findIndex((line) => /^jobs:\s*$/.test(line));
  if (jobsIndex === -1) {
    return null;
  }
  const jobPattern = new RegExp(`^  ${escapeRegExp(jobId)}:\\s*$`);
  const start = lines.findIndex(
    (line, index) => index > jobsIndex && jobPattern.test(line),
  );
  if (start === -1) {
    return null;
  }
  const block = [];
  for (let index = start + 1; index < lines.length; index += 1) {
    const line = lines[index];
    if (line.trim() === "") {
      block.push(line);
      continue;
    }
    if (/^  \S/.test(line)) {
      break;
    }
    block.push(line);
  }
  return block;
}

/** Splits the `needs:` value of a job block into a list of job IDs. */
function parseNeeds(needsLine) {
  if (needsLine === undefined) {
    return [];
  }
  return needsLine
    .slice(needsLine.indexOf(":") + 1)
    .replace(/[[\]]/g, "")
    .split(",")
    .map((entry) => entry.trim())
    .filter((entry) => entry !== "");
}

/**
 * The failure mode this exists to prevent (Issue #312 acceptance 2): renaming
 * `Package (Windows)` or mis-writing the alarm's condition must not leave a
 * monitor that silently never fires. Returns a list of problems; empty is
 * healthy.
 *
 * Issue #331 added a second wiring to guard: `quality` must need `package`.
 * (`quality` must also assert `needs.package.result` in its result loop, but
 * that is mutation-tested in real CI rather than guarded here -- a guard would
 * turn the "needs-only" mutation red through a different job and hide the
 * evidence that the loop is what blocks the merge.)
 */
export function verifyWorkflowWiring(ciYaml) {
  const problems = [];

  const packageBlock = jobBlock(ciYaml, PACKAGE_JOB_ID);
  if (packageBlock === null) {
    problems.push(`ci.yml has no \`${PACKAGE_JOB_ID}\` job`);
  } else {
    const nameLine = packageBlock.find((line) => /^    name:\s*/.test(line));
    const declaredName =
      nameLine === undefined
        ? undefined
        : nameLine.slice(nameLine.indexOf(":") + 1).trim();
    if (declaredName !== PACKAGE_JOB_NAME) {
      problems.push(
        `job \`${PACKAGE_JOB_ID}\` is named ${JSON.stringify(declaredName)} ` +
          `but the alarm reports ${JSON.stringify(PACKAGE_JOB_NAME)}`,
      );
    }
  }

  const qualityBlock = jobBlock(ciYaml, QUALITY_JOB_ID);
  if (qualityBlock === null) {
    problems.push(`ci.yml has no \`${QUALITY_JOB_ID}\` job`);
  } else {
    const qualityNeeds = parseNeeds(
      qualityBlock.find((line) => /^    needs:\s*/.test(line)),
    );
    if (!qualityNeeds.includes(PACKAGE_JOB_ID)) {
      problems.push(
        `\`${QUALITY_JOB_ID}\` does not need \`${PACKAGE_JOB_ID}\`; a red ` +
          `\`${PACKAGE_JOB_NAME}\` cannot block a merge (Issue #331)`,
      );
    }
  }

  const alarmBlock = jobBlock(ciYaml, ALARM_JOB_ID);
  if (alarmBlock === null) {
    problems.push(`ci.yml has no \`${ALARM_JOB_ID}\` job`);
    return problems;
  }

  const needs = parseNeeds(
    alarmBlock.find((line) => /^    needs:\s*/.test(line)),
  );
  if (!needs.includes(PACKAGE_JOB_ID)) {
    problems.push(
      `\`${ALARM_JOB_ID}\` does not need \`${PACKAGE_JOB_ID}\`; it would run ` +
        "before the package result exists",
    );
  }

  const ifLine = alarmBlock.find((line) => /^    if:\s*/.test(line));
  if (ifLine === undefined || !ifLine.includes("always()")) {
    problems.push(
      `\`${ALARM_JOB_ID}\` has no \`if: always()\`; a failing ` +
        `\`${PACKAGE_JOB_ID}\` would skip it, which GitHub shows as a pass`,
    );
  }

  return problems;
}

const invokedDirectly =
  process.argv[1] !== undefined &&
  import.meta.url === pathToFileURL(process.argv[1]).href;

if (invokedDirectly) {
  runPackageAlarm()
    .then((code) => {
      process.exitCode = code;
    })
    .catch((error) => {
      console.error(error instanceof Error ? error.message : String(error));
      process.exitCode = 1;
    });
}
