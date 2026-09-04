import {
  cpSync,
  existsSync,
  mkdirSync,
  readdirSync,
  readFileSync,
  rmSync,
  statSync,
} from "node:fs";
import { dirname, join, relative, resolve } from "node:path";
import { fileURLToPath } from "node:url";

/**
 * `.agents/skills/` を Canonical Source として、異なるSkill探索パスを使うAgent
 * （現状はClaude Codeの `.claude/skills/`）へSKILL.mdをコピー同期する薄い互換レイヤー。
 *
 *   node scripts/sync-agent-skills.mjs           # 同期する
 *   node scripts/sync-agent-skills.mjs --check   # 差分があれば非ゼロ終了（CI/検証用）
 */

const repoRoot = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const canonicalDir = join(repoRoot, ".agents", "skills");
const mirrorDirs = [join(repoRoot, ".claude", "skills")];
const checkOnly = process.argv.includes("--check");

function listSkillDirs(root) {
  if (!existsSync(root)) return [];
  return readdirSync(root, { withFileTypes: true })
    .filter((entry) => entry.isDirectory())
    .map((entry) => entry.name)
    .sort();
}

function listFiles(root) {
  const files = [];
  for (const entry of readdirSync(root, { withFileTypes: true })) {
    const full = join(root, entry.name);
    if (entry.isDirectory()) {
      files.push(...listFiles(full));
    } else if (entry.isFile()) {
      files.push(full);
    }
  }
  return files;
}

function dirsEqual(source, target) {
  if (!existsSync(target)) return false;
  const sourceFiles = listFiles(source)
    .map((f) => relative(source, f))
    .sort();
  const targetFiles = listFiles(target)
    .map((f) => relative(target, f))
    .sort();
  if (sourceFiles.join("\n") !== targetFiles.join("\n")) return false;
  return sourceFiles.every((rel) =>
    readFileSync(join(source, rel)).equals(readFileSync(join(target, rel))),
  );
}

const skills = listSkillDirs(canonicalDir);
if (skills.length === 0) {
  console.error(`No skills found in ${relative(repoRoot, canonicalDir)}`);
  process.exit(1);
}

const drift = [];

for (const mirrorDir of mirrorDirs) {
  const mirrorLabel = relative(repoRoot, mirrorDir);

  for (const skill of skills) {
    const source = join(canonicalDir, skill);
    const target = join(mirrorDir, skill);
    if (dirsEqual(source, target)) continue;

    drift.push(`${mirrorLabel}/${skill}`);
    if (checkOnly) continue;

    rmSync(target, { recursive: true, force: true });
    mkdirSync(dirname(target), { recursive: true });
    cpSync(source, target, { recursive: true });
    console.log(`synced  ${mirrorLabel}/${skill}`);
  }

  // Canonicalから消えたSkillはミラーからも削除する
  for (const stale of listSkillDirs(mirrorDir)) {
    if (skills.includes(stale)) continue;
    const target = join(mirrorDir, stale);
    if (!statSync(target).isDirectory()) continue;

    drift.push(`${mirrorLabel}/${stale} (stale)`);
    if (checkOnly) continue;

    rmSync(target, { recursive: true, force: true });
    console.log(`removed ${mirrorLabel}/${stale}`);
  }
}

if (checkOnly && drift.length > 0) {
  console.error("Agent skill mirrors are out of sync:");
  for (const item of drift) console.error(`  - ${item}`);
  console.error("Run: pnpm skills:sync");
  process.exit(1);
}

if (checkOnly) {
  console.log("Agent skill mirrors are in sync.");
} else if (drift.length === 0) {
  console.log("Agent skill mirrors already in sync.");
}
