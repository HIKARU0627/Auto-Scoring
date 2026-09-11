import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync } from "node:fs";
import { builtinModules } from "node:module";
import * as path from "node:path";

/**
 * Dependency-direction test for `desktop/`.
 *
 * Same role as `app/test/architecture_test.dart` and
 * `backend/tests/test_architecture.py`: the layering is a rule the machine
 * enforces, not a convention people remember. Here it also carries the security
 * boundary -- `contextIsolation: true` / `nodeIntegration: false` /
 * `sandbox: true` is what makes "the renderer has no Node" true at runtime, and
 * the import rules below are what keep the source honest about it.
 *
 * A negative assertion goes vacuous when whatever it was watching stops
 * existing, so this file is verified by breaking it on purpose: the procedure
 * and its result are in the pull request for Issue #217.
 */

const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const SOURCE_EXTENSIONS = new Set([".ts", ".tsx", ".mts", ".cts"]);

/** `fs`, `node:fs`, `fs/promises`, ... -- everything Node ships with. */
const NODE_BUILTINS = new Set(builtinModules);

function isNodeBuiltin(specifier: string): boolean {
  const withoutPrefix = specifier.startsWith("node:")
    ? specifier.slice("node:".length)
    : specifier;
  const root = withoutPrefix.split("/")[0] ?? "";
  return specifier.startsWith("node:") || NODE_BUILTINS.has(root);
}

function isElectron(specifier: string): boolean {
  return specifier === "electron" || specifier.startsWith("electron/");
}

function isReact(specifier: string): boolean {
  const root = specifier.startsWith("@")
    ? specifier.split("/").slice(0, 2).join("/")
    : (specifier.split("/")[0] ?? "");
  return (
    root === "react" ||
    root === "react-dom" ||
    root === "react-router" ||
    root === "@testing-library/react"
  );
}

/**
 * Replaces comments and string bodies with spaces so the specifier patterns
 * below cannot match a module name that only appears in prose. Without this, a
 * comment explaining *why* the renderer must not `import { app } from "electron"`
 * would itself fail the test -- and the fix people would reach for is deleting
 * the explanation.
 */
function blankCommentsAndStrings(source: string): string {
  const out: string[] = [];
  let index = 0;
  // Keeping the quote character in the output (and blanking only the body) is
  // what lets the specifier patterns still see `from ""` and report an empty
  // specifier instead of silently matching the next line.
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

/**
 * The specifier is read from the *blanked* source, so it is recovered from the
 * original text at the same offset.
 */
const SPECIFIER_PATTERNS: readonly RegExp[] = [
  /\bfrom\s*["'`]/g, // import x from "y" / export { x } from "y"
  /\bimport\s*\(\s*["'`]/g, // await import("y")
  /\brequire\s*\(\s*["'`]/g, // require("y")
  /\bimport\s+["'`]/g, // import "y"
];

function importedSpecifiers(source: string): string[] {
  const blanked = blankCommentsAndStrings(source);
  const specifiers: string[] = [];
  for (const pattern of SPECIFIER_PATTERNS) {
    pattern.lastIndex = 0;
    let match: RegExpExecArray | null = pattern.exec(blanked);
    while (match !== null) {
      const quote = blanked[match.index + match[0].length - 1] as string;
      const end = blanked.indexOf(quote, match.index + match[0].length);
      if (end !== -1) {
        specifiers.push(source.slice(match.index + match[0].length, end));
      }
      match = pattern.exec(blanked);
    }
  }
  return specifiers;
}

function sourceFilesUnder(relativeDir: string): string[] {
  const absolute = path.join(PACKAGE_ROOT, relativeDir);
  const found: string[] = [];
  for (const entry of readdirSync(absolute, {
    withFileTypes: true,
    recursive: true,
  })) {
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

interface LayerRule {
  /** Directory the rule applies to, relative to `desktop/`. */
  readonly layer: string;
  /** Directories this layer may reach with a relative import. */
  readonly mayImportFrom: readonly string[];
  /** Returns why the package is forbidden here, or `null` if it is allowed. */
  readonly forbiddenPackage: (specifier: string) => string | null;
  /**
   * Relative imports this rule tolerates because they already exist and are
   * owned by another in-flight change. Kept as exact (file, target) pairs, not
   * a count: adding another violation to the same file still fails.
   */
  readonly allowlist?: readonly AllowedSubLayerImport[];
}

interface AllowedSubLayerImport {
  /** Importing file, relative to `desktop/`. */
  readonly file: string;
  /** Resolved target of the relative import, relative to `desktop/`. */
  readonly target: string;
}

/**
 * INV-001: `api` must not import `core` / `features`; INV-002: `core` must not
 * import `features`.
 *
 * The six hand-written `api/*-data.ts` loaders that pulled in `core` (domain
 * models, errors, review state) were moved to `core/`, because composing an API
 * response into a domain object is a core responsibility. The one remaining
 * reverse reference is owned by Issue #255, which is editing that file, so it is
 * allowed here by exact pair. Remove the entry once #255 lands.
 *
 * TODO(owner): replace with the Issue number that removes this allowlist entry.
 */
const OUTSTANDING_API_IMPORTS: readonly AllowedSubLayerImport[] = [
  {
    file: "src/renderer/api/answer-area-data.ts",
    target: "src/renderer/features/answer-area-editor/answer-area-types.js",
  },
];

/** Fixed so that appending another allowlisted violation turns the test red. */
const OUTSTANDING_API_IMPORT_COUNT = 1;

const RULES: readonly LayerRule[] = [
  {
    layer: "src/renderer",
    mayImportFrom: ["src/renderer", "src/shared"],
    forbiddenPackage: (specifier) => {
      if (isElectron(specifier)) {
        return "the renderer runs with contextIsolation and no Node integration; everything from the main process arrives through the preload bridge (src/shared/bridge.ts)";
      }
      if (isNodeBuiltin(specifier)) {
        return "the renderer has no Node runtime; a build that resolves this would either fail at runtime or mean the sandbox was turned off";
      }
      return null;
    },
  },
  {
    // INV-001: `api` is the backend client. It may talk to another `api` module
    // or the shared bridge contract, but it must not reach up into `core`
    // (domain) or `features` (screens) -- those depend on it, not the reverse.
    layer: "src/renderer/api",
    mayImportFrom: ["src/renderer/api", "src/shared"],
    forbiddenPackage: () => null,
    allowlist: OUTSTANDING_API_IMPORTS,
  },
  {
    // INV-002: `core` may use the generated client (`api`) and the shared
    // contract, but it must not import a screen (`features`). `core` is where
    // domain logic lives, so `features -> core -> api` stays one-way.
    layer: "src/renderer/core",
    mayImportFrom: ["src/renderer/core", "src/renderer/api", "src/shared"],
    forbiddenPackage: () => null,
  },
  {
    layer: "src/preload",
    mayImportFrom: ["src/preload", "src/shared"],
    forbiddenPackage: (specifier) => {
      if (isNodeBuiltin(specifier)) {
        return "a sandboxed preload script has only a polyfilled subset of Node; keep it to `electron` and the shared contract";
      }
      if (isReact(specifier)) {
        return "the preload script is the boundary, not the UI";
      }
      return null;
    },
  },
  {
    layer: "src/main",
    mayImportFrom: ["src/main", "src/shared"],
    forbiddenPackage: (specifier) =>
      isReact(specifier)
        ? "the main process has no DOM; UI code belongs in src/renderer"
        : null,
  },
  {
    layer: "src/shared",
    mayImportFrom: ["src/shared"],
    forbiddenPackage: (specifier) => {
      if (
        isElectron(specifier) ||
        isNodeBuiltin(specifier) ||
        isReact(specifier)
      ) {
        return "src/shared is read by both sides of the bridge, so it must stay free of anything only one side can load";
      }
      return null;
    },
  },
];

describe("dependency direction", () => {
  for (const rule of RULES) {
    describe(rule.layer, () => {
      const files = sourceFilesUnder(rule.layer);

      it("has source files to check", () => {
        // Without this, deleting or renaming the layer would turn every
        // assertion below into a loop over an empty list that passes.
        expect(files.length).toBeGreaterThan(0);
      });

      for (const file of files) {
        it(`${file} imports nothing it must not`, () => {
          const source = readFileSync(path.join(PACKAGE_ROOT, file), "utf8");
          const violations: string[] = [];

          for (const specifier of importedSpecifiers(source)) {
            if (specifier.startsWith(".")) {
              const target = path
                .relative(
                  PACKAGE_ROOT,
                  path.resolve(PACKAGE_ROOT, path.dirname(file), specifier),
                )
                .split(path.sep)
                .join("/");
              const allowed = rule.mayImportFrom.some(
                (dir) => target === dir || target.startsWith(`${dir}/`),
              );
              if (!allowed) {
                const allowlisted =
                  rule.allowlist?.some(
                    (entry) => entry.file === file && entry.target === target,
                  ) ?? false;
                if (allowlisted) {
                  continue;
                }
                violations.push(
                  `${specifier} -> ${target}: ${rule.layer} may only import from ${rule.mayImportFrom.join(", ")}`,
                );
              }
              continue;
            }

            const reason = rule.forbiddenPackage(specifier);
            if (reason !== null) {
              violations.push(`${specifier}: ${reason}`);
            }
          }

          expect(violations).toEqual([]);
        });
      }
    });
  }
});

describe("INV-001 tolerated reverse references", () => {
  it("are a fixed-size, unambiguous list", () => {
    // The count is a tripwire, not a budget: growing the allowlist (or adding a
    // second matching violation) has to edit this test, which is what a
    // reviewer notices. Unique pairs keep one entry from hiding two imports.
    expect(OUTSTANDING_API_IMPORTS).toHaveLength(OUTSTANDING_API_IMPORT_COUNT);
    const keys = OUTSTANDING_API_IMPORTS.map(
      (entry) => `${entry.file}\0${entry.target}`,
    );
    expect(new Set(keys).size).toBe(keys.length);
  });
});

describe("the bridge carries no raw bytes", () => {
  // Issue #207 approval condition 3: the Python sidecar owns app-data, so a
  // PDF's bytes never travel to the renderer. The moment one of these types
  // appears in the contract, somebody is about to pass a page image through IPC.
  const BINARY_TYPES = [
    "ArrayBuffer",
    "SharedArrayBuffer",
    "ArrayBufferView",
    "Uint8Array",
    "Uint8ClampedArray",
    "Buffer",
    "Blob",
    "DataView",
    "File",
    "ReadableStream",
  ];

  it("src/shared/bridge.ts declares no binary payload type", () => {
    const source = readFileSync(
      path.join(PACKAGE_ROOT, "src/shared/bridge.ts"),
      "utf8",
    );
    const code = blankCommentsAndStrings(source);
    const found = BINARY_TYPES.filter((type) =>
      new RegExp(`\\b${type}\\b`).test(code),
    );
    expect(found).toEqual([]);
  });
});

describe("the window keeps the renderer untrusted", () => {
  // The import rules above are only meaningful while these three hold: they are
  // what actually removes Node from the renderer at runtime.
  const REQUIRED = [
    "contextIsolation: true",
    "nodeIntegration: false",
    "sandbox: true",
  ];

  it("src/main/main.ts sets every switch that isolates the renderer", () => {
    const source = readFileSync(
      path.join(PACKAGE_ROOT, "src/main/main.ts"),
      "utf8",
    );
    const code = blankCommentsAndStrings(source);
    const missing = REQUIRED.filter((setting) => !code.includes(setting));
    expect(missing).toEqual([]);
  });
});
