// Fails when a canonical enum code or label appears as a whole string literal under src/.
// The enum values come from tests/fixtures/enums.json (the body of GET /meta/enums).
// A line may opt out with the marker `check-enums: allow` in a comment; this is reserved for
// protocol state logic that has to compare codes, never for display text.
import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

const root = process.cwd();
const srcDir = path.join(root, "src");
const fixturePath = path.join(root, "tests", "fixtures", "enums.json");
const EXTENSIONS = new Set([".ts", ".tsx", ".js", ".jsx", ".mjs"]);
const ALLOW_MARKER = "check-enums: allow";

function loadValues() {
  const data = JSON.parse(readFileSync(fixturePath, "utf8"));
  const values = new Set();
  for (const entry of data.enums) {
    for (const item of entry.values) {
      values.add(item.code);
      values.add(item.label);
    }
  }
  return values;
}

function* walk(dir) {
  for (const name of readdirSync(dir)) {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) yield* walk(full);
    else if (EXTENSIONS.has(path.extname(name))) yield full;
  }
}

const LITERAL = /"((?:[^"\\\n]|\\.)*)"|'((?:[^'\\\n]|\\.)*)'|`((?:[^`\\$]|\\.)*)`/g;

const values = loadValues();
const findings = [];
for (const file of walk(srcDir)) {
  const lines = readFileSync(file, "utf8").split("\n");
  lines.forEach((line, index) => {
    if (line.includes(ALLOW_MARKER)) return;
    for (const match of line.matchAll(LITERAL)) {
      const literal = match[1] ?? match[2] ?? match[3] ?? "";
      if (values.has(literal)) {
        findings.push(`${path.relative(root, file)}:${index + 1}: enum literal "${literal}"`);
      }
    }
  });
}

if (findings.length > 0) {
  console.error("check-enums: enum codes and labels must come from /meta/enums, found:");
  for (const finding of findings) console.error(`  ${finding}`);
  process.exit(1);
}
console.log("check-enums: no enum literal found under frontend/src.");
