import { describe, expect, it } from "vitest";
import { readFileSync, readdirSync, type Dirent } from "node:fs";
import * as path from "node:path";

/**
 * Navigation / routing invariants carried over from the Flutter app
 * (`docs/frontend-invariants.md` §3, rows INV-010 / INV-011; Issue #322).
 *
 * - INV-010: `features/` never reaches for `go_router`'s destructive
 *   `.go()` / `.goNamed()` jump. A screen that can discard the stack leaves the
 *   user with no Back / Escape route, which is the bug #160 fixed.
 * - INV-011: screen-to-screen movement is `push` / `replace` / `pop` only. The
 *   router's command surface is exactly those three methods, so no screen can
 *   invent a fourth transition that behaves differently depending on how it was
 *   opened.
 *
 * Both promises are structural in the Electron stack: the renderer has its own
 * router instead of `go_router`, so the failure cannot happen while the shapes
 * below hold. These tests are the tripwires that go red the moment someone
 * reintroduces the shape. The scanners carry a positive-control fixture so a
 * renamed directory or a broken regex cannot leave them passing vacuously.
 */

const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const FEATURES_DIR = path.join(PACKAGE_ROOT, "src/renderer/features");
const ROUTER_PATH = path.join(
  PACKAGE_ROOT,
  "src/renderer/navigation/router.tsx",
);
const SOURCE_EXTENSIONS = new Set([".ts", ".tsx"]);

/**
 * Lower bound on the feature tree the scanner walks. `design-tokens-lint.test.ts`
 * uses the same shape: if the tree shrinks below this, fail rather than scan an
 * empty (or renamed) directory and report success.
 */
const EXPECTED_MIN_FEATURE_FILES = 24;

/**
 * `go_router`'s destructive jump, however it is spelled: `.go("...")` or
 * `.goNamed("...")`. `.going(` is not a match because a call needs `(`.
 */
const DESTRUCTIVE_NAVIGATION = /\.(?:go|goNamed)\s*\(/g;

interface CommandSurface {
  readonly methods: readonly string[];
  /** The extracted interface body, for error messages. */
  readonly body: string;
}

/**
 * Replaces comments and string bodies with spaces so `.go()` in a comment or a
 * message does not count as source. Keeping the quote characters lets the
 * interface scanner still see `readonly push: (path: string) => void`.
 */
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

function featureFiles(): string[] {
  const found: string[] = [];
  let entries: Dirent[];
  try {
    entries = readdirSync(FEATURES_DIR, {
      withFileTypes: true,
      recursive: true,
    });
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

/** `.go()` / `.goNamed()` calls in real code (comments and strings blanked). */
function detectDestructiveNavigation(source: string): string[] {
  return [...blankCommentsAndStrings(source).matchAll(DESTRUCTIVE_NAVIGATION)]
    .map((match) => match[0].replace(/\s+/g, ""))
    .sort();
}

/** The callable members declared by the router's context interface. */
function routerCommandSurface(source: string): CommandSurface {
  const match = /interface RouterContextValue\s*\{([\s\S]*?)\n\s*\}/.exec(
    blankCommentsAndStrings(source),
  );
  const body = match?.[1];
  if (body === undefined) {
    throw new Error(
      "router.tsx の RouterContextValue interface を読めませんでした。" +
        "名前を変えたなら、この検査も合わせて更新すること。",
    );
  }
  const methods = [
    ...body.matchAll(/^\s*(?:readonly\s+)?([A-Za-z0-9_]+)\s*:\s*\(/gm),
  ]
    .map((entry) => entry[1] as string)
    .sort();
  return { methods, body };
}

describe("navigation never discards the stack (INV-010)", () => {
  it("scans at least the expected number of features files (prevents a vacuous pass)", () => {
    const files = featureFiles();
    expect(
      files.length,
      `Expected >= ${EXPECTED_MIN_FEATURE_FILES} features files to be scanned, found ${files.length}`,
    ).toBeGreaterThanOrEqual(EXPECTED_MIN_FEATURE_FILES);
  });

  it("the scanner flags `.go()` / `.goNamed()` and ignores prose and other calls", () => {
    // Positive control: the scanner itself must find the destructive jump.
    const fixture = [
      "// go_router had router.go('/x') and router.goNamed('x')",
      "function Screen() {",
      "  const router = useRouter();",
      '  router.go("/intake");',
      '  router.goNamed("home");',
      "  return null;",
      "}",
    ].join("\n");
    expect(detectDestructiveNavigation(fixture)).toEqual([".go(", ".goNamed("]);
  });

  it("features/ contains no go_router jump", () => {
    const violations = featureFiles().flatMap((file) => {
      const source = readFileSync(path.join(PACKAGE_ROOT, file), "utf8");
      return detectDestructiveNavigation(source).map(
        (token) => `${file}: ${token}`,
      );
    });
    expect(violations).toEqual([]);
  });
});

describe("transitions are push / replace / pop only (INV-011)", () => {
  it("the scanner reads the command methods from an interface", () => {
    // Positive control: an interface that grew a fourth command is reported.
    const fixture = `
      interface RouterContextValue {
        readonly location: string;
        readonly canPop: boolean;
        readonly push: (path: string) => void;
        readonly replace: (path: string) => void;
        readonly pop: () => void;
        readonly go: (path: string) => void;
      }
    `;
    expect(routerCommandSurface(fixture).methods).toEqual([
      "go",
      "pop",
      "push",
      "replace",
    ]);
  });

  it("RouterContextValue exposes exactly push / replace / pop as commands", () => {
    const source = readFileSync(ROUTER_PATH, "utf8");
    const surface = routerCommandSurface(source);
    expect(
      surface.methods,
      `RouterContextValue の関数メンバが変わっています:\n${surface.body.trim()}`,
    ).toEqual(["pop", "push", "replace"]);
  });
});
