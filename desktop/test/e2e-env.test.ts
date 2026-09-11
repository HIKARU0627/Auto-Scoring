import { readFileSync, readdirSync } from "node:fs";
import * as path from "node:path";
import { describe, expect, it, vi } from "vitest";

const mockIsPackaged = vi.hoisted(() => ({ value: false }));

vi.mock("electron", () => ({
  app: {
    get isPackaged() {
      return mockIsPackaged.value;
    },
  },
}));

import { readE2eEnv } from "../src/main/e2e-env.js";

const PACKAGE_ROOT = path.resolve(import.meta.dirname, "..");
const MAIN_DIR = path.join(PACKAGE_ROOT, "src/main");
const SOURCE_EXTENSIONS = new Set([".ts"]);

function collectMainSources(): string[] {
  const files: string[] = [];
  for (const entry of readdirSync(MAIN_DIR, { withFileTypes: true })) {
    const absolute = path.join(MAIN_DIR, entry.name);
    if (entry.isDirectory()) {
      for (const nested of readdirSync(absolute, { withFileTypes: true })) {
        if (
          nested.isFile() &&
          SOURCE_EXTENSIONS.has(path.extname(nested.name))
        ) {
          files.push(path.join(absolute, nested.name));
        }
      }
      continue;
    }
    if (entry.isFile() && SOURCE_EXTENSIONS.has(path.extname(entry.name))) {
      files.push(absolute);
    }
  }
  return files.sort();
}

describe("readE2eEnv (UG-05)", () => {
  it("ignores E2E overrides when the app is packaged", () => {
    mockIsPackaged.value = true;
    const env = {
      AUTO_SCORING_E2E_FOLDER: "/tmp/e2e-folder",
      AUTO_SCORING_E2E_PDF: "/tmp/e2e.pdf",
      AUTO_SCORING_E2E_APP_DATA: "/tmp/e2e-app-data",
    };

    expect(readE2eEnv("AUTO_SCORING_E2E_FOLDER", env)).toBeUndefined();
    expect(readE2eEnv("AUTO_SCORING_E2E_PDF", env)).toBeUndefined();
    expect(readE2eEnv("AUTO_SCORING_E2E_APP_DATA", env)).toBeUndefined();
  });

  it("returns non-empty values only for unpackaged builds", () => {
    mockIsPackaged.value = false;
    const env = {
      AUTO_SCORING_E2E_FOLDER: "/tmp/e2e-folder",
      AUTO_SCORING_E2E_PDF: "",
    };

    expect(readE2eEnv("AUTO_SCORING_E2E_FOLDER", env)).toBe("/tmp/e2e-folder");
    expect(readE2eEnv("AUTO_SCORING_E2E_PDF", env)).toBeUndefined();
    expect(readE2eEnv("AUTO_SCORING_E2E_MISSING", env)).toBeUndefined();
  });
});

describe("readE2eEnv packaged gate (UG-05)", () => {
  it("reads app.isPackaged inside e2e-env.ts (not from caller parameters)", () => {
    const source = readFileSync(
      path.join(PACKAGE_ROOT, "src/main/e2e-env.ts"),
      "utf8",
    );
    expect(source).toMatch(/app\.isPackaged/);
    expect(source).toMatch(/from "electron"/);
    expect(source).not.toMatch(/\bisPackaged:\s*boolean\b/);
  });

  it("main process call sites invoke readE2eEnv without a caller-supplied packaged flag", () => {
    const mainSources = collectMainSources();
    expect(mainSources.length).toBeGreaterThan(0);

    const callSites = mainSources.flatMap((file) => {
      const source = readFileSync(file, "utf8");
      const matches = [...source.matchAll(/\breadE2eEnv\s*\(/g)];
      return matches.map((match) => ({
        file: path.relative(PACKAGE_ROOT, file),
        index: match.index ?? 0,
        snippet: source.slice(match.index ?? 0, (match.index ?? 0) + 80),
      }));
    });

    expect(callSites.length).toBeGreaterThan(0);
    for (const site of callSites) {
      expect(site.snippet).not.toMatch(/readE2eEnv\s*\([^,]+,\s*false/);
      expect(site.snippet).not.toMatch(
        /readE2eEnv\s*\([^,]+,\s*app\.isPackaged/,
      );
    }
  });
});
