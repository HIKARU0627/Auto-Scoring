import { readFileSync } from "node:fs";
import * as path from "node:path";
import { fileURLToPath } from "node:url";

export type ThemeName = "light" | "dark";

const TOKENS_PATH = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../src/renderer/styles/design-tokens.css",
);

const BLOCK_PATTERNS: Record<ThemeName, RegExp> = {
  light:
    /:root,\s*\[data-theme="light"\]\s*\{([\s\S]*?)\}\s*\[data-theme="dark"\]/,
  dark: /\[data-theme="dark"\]\s*\{([\s\S]*?)\}\s*$/,
};

function parseDeclarations(block: string): Map<string, string> {
  const vars = new Map<string, string>();
  for (const match of block.matchAll(/(--[\w-]+)\s*:\s*([^;]+);/g)) {
    const name = match[1];
    const value = match[2];
    if (name === undefined || value === undefined) {
      continue;
    }
    vars.set(name, value.trim());
  }
  return vars;
}

function resolveVar(
  name: string,
  vars: Map<string, string>,
  stack: string[] = [],
): string {
  const raw = vars.get(name);
  if (raw === undefined) {
    throw new Error(`missing token ${name}`);
  }
  const varMatch = /^var\((--[\w-]+)\)$/.exec(raw);
  if (varMatch === null) {
    return raw;
  }
  const target = varMatch[1];
  if (target === undefined) {
    throw new Error(`malformed var() in ${name}`);
  }
  if (stack.includes(target)) {
    throw new Error(`circular var() chain: ${[...stack, target].join(" -> ")}`);
  }
  return resolveVar(target, vars, [...stack, name]);
}

/** Read resolved token values for one theme from `design-tokens.css`. */
export function readThemeTokens(theme: ThemeName): Map<string, string> {
  const css = readFileSync(TOKENS_PATH, "utf8");
  const pattern = BLOCK_PATTERNS[theme];
  const match = pattern.exec(css);
  const block = match?.[1];
  if (block === undefined) {
    throw new Error(`could not parse ${theme} block in design-tokens.css`);
  }
  const declarations = parseDeclarations(block);
  const resolved = new Map<string, string>();
  for (const name of declarations.keys()) {
    resolved.set(name, resolveVar(name, declarations));
  }
  return resolved;
}

export function tokenHex(
  tokens: Map<string, string>,
  name: `--${string}`,
): string {
  const value = tokens.get(name);
  if (value === undefined) {
    throw new Error(`token ${name} is not defined`);
  }
  return value;
}
