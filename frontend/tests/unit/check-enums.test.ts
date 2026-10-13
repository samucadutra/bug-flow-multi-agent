import { spawnSync } from "node:child_process";
import { cpSync, mkdirSync, mkdtempSync, rmSync, writeFileSync } from "node:fs";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";

const script = path.resolve(import.meta.dirname, "../../scripts/check-enums.mjs");
const fixtures = path.resolve(import.meta.dirname, "../fixtures");
const created: string[] = [];

function project(source: string): string {
  const dir = mkdtempSync(path.join(os.tmpdir(), "check-enums-"));
  created.push(dir);
  mkdirSync(path.join(dir, "src"));
  mkdirSync(path.join(dir, "tests"));
  cpSync(fixtures, path.join(dir, "tests", "fixtures"), { recursive: true });
  writeFileSync(path.join(dir, "src", "sample.tsx"), source);
  return dir;
}

function run(dir: string) {
  return spawnSync("node", [script], { cwd: dir, encoding: "utf8" });
}

afterEach(() => {
  while (created.length > 0) rmSync(created.pop() as string, { recursive: true, force: true });
});

describe("check-enums", () => {
  it("passes on a clean tree", () => {
    const result = run(project('export const title = "Dashboard";\n'));
    expect(result.status).toBe(0);
    expect(result.stdout).toContain("no enum literal found under frontend/src");
  });

  it("test_check_enums_flags_literal", () => {
    const result = run(project('export const label = "Needs info";\n'));
    expect(result.status).not.toBe(0);
    expect(result.stderr).toContain("sample.tsx");
    expect(result.stderr).toContain("Needs info");
  });

  it("flags codes and honours the allow marker", () => {
    expect(run(project("const x = 'wont_fix';\n")).status).not.toBe(0);
    expect(run(project('const x = "failed"; // check-enums: allow (protocol)\n')).status).toBe(0);
  });
});
