import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, type Dirent } from "node:fs";
import * as path from "node:path";

/**
 * Sidecar lifecycle invariants carried over from the Flutter app
 * (`docs/frontend-invariants.md` §4 and §14, rows UG-02 / UG-03 / UG-04;
 * Issue #322).
 *
 * Flutter adopted Windows Job Objects so the sidecar died with the app. The
 * Electron stack deliberately dropped the native Job Object add-on (Issue #211,
 * #234, PR #237) because it cannot be verified on the Linux CI, and replaced it
 * with a parent-pid watchdog: the sidecar is told the Electron pid as a spawn
 * argument and watches it itself. That removes the three failure modes the Job
 * path had:
 *
 * - UG-02: a Job whose kill-on-close limit could not be set must not be kept.
 * - UG-03: a Job handle must not be closed while the process is alive.
 * - UG-04: the child must be registered the instant it is spawned.
 *
 * With no Job Object and `--parent-pid` built into the spawn arguments, all
 * three cannot happen. These tests are the tripwires: reintroducing a Job
 * Object API, or dropping `--parent-pid` from the spawn call, turns them red.
 */

const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const MAIN_DIR = path.join(PACKAGE_ROOT, "src/main");
const SUPERVISOR_PATH = path.join(MAIN_DIR, "sidecar-supervisor.ts");
const SOURCE_EXTENSIONS = new Set([".ts", ".tsx"]);

/**
 * UG-02: creating a Job and adopting a child without being able to set
 * kill-on-close. Any one of these means a Job Object path is back.
 */
const JOB_LIMIT_TOKENS = [
  "CreateJobObject",
  "CreateJobObjectW",
  "SetInformationJobObject",
  "AssignProcessToJobObject",
  "JOBOBJECT",
] as const;

/** UG-03: keeping a Job handle alive is only safe if it is never closed. */
const JOB_HANDLE_TOKENS = [
  "CloseHandle",
  "jobHandle",
  "JobHandle",
  "TerminateJobObject",
] as const;

/** Lower bound so a renamed directory cannot make the scan pass on nothing. */
const EXPECTED_MIN_MAIN_FILES = 8;

function sourceFilesUnder(dir: string): string[] {
  const found: string[] = [];
  let entries: Dirent[];
  try {
    entries = readdirSync(dir, { withFileTypes: true, recursive: true });
  } catch {
    return [];
  }
  for (const entry of entries) {
    if (!entry.isFile() || !SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
      continue;
    }
    found.push(
      path
        .relative(PACKAGE_ROOT, path.join(entry.parentPath, entry.name))
        .split(path.sep)
        .join("/"),
    );
  }
  return found.sort();
}

/** Blanks comments and string bodies so prose about a token is not a hit. */
function blankCommentsAndStrings(source: string): string {
  const out: string[] = [];
  let index = 0;
  while (index < source.length) {
    const two = source.slice(index, index + 2);
    if (two === "//") {
      while (index < source.length && source[index] !== "\n") {
        out.push(" ");
        index += 1;
      }
      continue;
    }
    if (two === "/*") {
      while (index < source.length && source.slice(index, index + 2) !== "*/") {
        out.push(source[index] === "\n" ? "\n" : " ");
        index += 1;
      }
      out.push(" ", " ");
      index += 2;
      continue;
    }
    const quote = source[index];
    if (quote === '"' || quote === "'" || quote === "`") {
      out.push(quote);
      index += 1;
      while (index < source.length && source[index] !== quote) {
        if (source[index] === "\\") {
          out.push(" ");
          index += 1;
        }
        out.push(source[index] === "\n" ? "\n" : " ");
        index += 1;
      }
      out.push(quote);
      index += 1;
      continue;
    }
    out.push(source[index] as string);
    index += 1;
  }
  return out.join("");
}

function detectTokens(source: string, tokens: readonly string[]): string[] {
  const code = blankCommentsAndStrings(source);
  return tokens.filter((token) => new RegExp(`\\b${token}\\b`).test(code));
}

function scanMain(tokens: readonly string[]): string[] {
  return sourceFilesUnder(MAIN_DIR).flatMap((file) =>
    detectTokens(
      readFileSync(path.join(PACKAGE_ROOT, file), "utf8"),
      tokens,
    ).map((token) => `${file}: ${token}`),
  );
}

/**
 * The argument list the supervisor hands to `platform.start`. The parent-pid
 * registration must live here: if it is not part of the spawn call, there is a
 * window between spawn and registration (UG-04).
 */
function spawnArgsBlock(source: string): string {
  const match = /const args = \[([\s\S]*?)\n\s*\];/.exec(source);
  const block = match?.[1];
  if (block === undefined) {
    throw new Error(
      "sidecar-supervisor.ts の `const args = [...]` を読めませんでした。" +
        " spawn 引数の組み立てを変えたなら、この検査も合わせて更新すること。",
    );
  }
  return block;
}

describe("no Win32 Job Object path returns (UG-02 / UG-03)", () => {
  it("scans at least the expected number of main files (prevents a vacuous pass)", () => {
    const files = sourceFilesUnder(MAIN_DIR);
    expect(
      files.length,
      `Expected >= ${EXPECTED_MIN_MAIN_FILES} main files to be scanned, found ${files.length}`,
    ).toBeGreaterThanOrEqual(EXPECTED_MIN_MAIN_FILES);
  });

  it("the scanner recognises Job Object APIs (positive control)", () => {
    const fixture = [
      "// Job Object review (UG-02/UG-03)",
      "const job = CreateJobObjectW(null, null);",
      "SetInformationJobObject(job, info);",
      "AssignProcessToJobObject(job, child);",
      "CloseHandle(job);",
      "const jobHandle = job;",
    ].join("\n");
    expect(detectTokens(fixture, JOB_LIMIT_TOKENS)).toEqual([
      "CreateJobObjectW",
      "SetInformationJobObject",
      "AssignProcessToJobObject",
    ]);
    expect(detectTokens(fixture, JOB_HANDLE_TOKENS)).toEqual([
      "CloseHandle",
      "jobHandle",
    ]);
  });

  it("UG-02: no Job is created/adopted, so a limit-less Job cannot be kept", () => {
    expect(scanMain(JOB_LIMIT_TOKENS)).toEqual([]);
  });

  it("UG-03: no Job handle lifecycle exists, so it cannot be closed early", () => {
    expect(scanMain(JOB_HANDLE_TOKENS)).toEqual([]);
  });
});

describe("the parent watchdog is armed inside the spawn call (UG-04)", () => {
  it("the parser reads the spawn argument list (positive control)", () => {
    const fixture = `
      const args = [
        "--port",
        "0",
        "--handshake-file",
        filePath,
      ];
    `;
    expect(spawnArgsBlock(fixture)).toContain('"--port"');
    expect(spawnArgsBlock(fixture)).not.toContain("--parent-pid");
  });

  it("--parent-pid is passed with the current pid as part of spawn", () => {
    const block = spawnArgsBlock(readFileSync(SUPERVISOR_PATH, "utf8"));
    expect(
      block,
      "UG-04: spawn 引数に --parent-pid が無い（登録が spawn 後へ戻っている）",
    ).toContain('"--parent-pid"');
    expect(
      block,
      "UG-04: --parent-pid の値が currentPid() から作られていない",
    ).toContain("String(this._platform.currentPid())");
  });
});
