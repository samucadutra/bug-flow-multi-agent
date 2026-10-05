import {
  chmodSync,
  existsSync,
  lstatSync,
  mkdirSync,
  readFileSync,
  readlinkSync,
  symlinkSync,
  writeFileSync,
} from "node:fs";
import { dirname, join } from "node:path";
import { destinationFor, walk } from "./templates.mjs";

const EXECUTABLE = new Set([
  "scripts/init.sh",
  "scripts/stop.sh",
  "scripts/migrate-dev.sh",
  "scripts/run-gates.mjs",
  "scripts/spawn-detached.mjs",
]);

export function writeTemplates(plan) {
  writeTemplateGroups(plan, plan.groups);
  writeClaudeSymlink(plan);
}

export function writeTemplateGroups(plan, groups, options = {}) {
  const created = new Set();
  plan.createdFiles ??= new Set();
  for (const group of groups) {
    writeGroup(plan, group, created, options);
  }
}

export function writeClaudeSymlink(plan) {
  const destination = join(plan.target, "CLAUDE.md");
  if (existsSync(destination) && !isExpectedClaudeSymlink(destination)) {
    throw new Error(`Refusing to overwrite existing file: ${destination}`);
  }
  if (!existsSync(destination)) symlinkSync("AGENTS.md", destination);
  plan.createdFiles ??= new Set();
  plan.createdFiles.add(destination);
}

function writeGroup(plan, group, created, options) {
  const sourceDir = join(plan.templateDir, group);
  for (const source of walk(sourceDir)) {
    const relativePath = source.slice(sourceDir.length + 1);
    const destination = join(plan.target, destinationFor(group, relativePath));
    writeTemplateFile(plan, source, destination, created, options);
  }
}

function writeTemplateFile(plan, source, destination, created, options) {
  if (existsSync(destination) && !created.has(destination) && !options.allowOverwrite) {
    throw new Error(`Refusing to overwrite existing file: ${destination}`);
  }
  mkdirSync(dirname(destination), { recursive: true });
  writeFileSync(destination, render(readFileSync(source, "utf8"), plan.replacements));
  created.add(destination);
  plan.createdFiles.add(destination);
  chmodIfScript(plan, destination);
}

function render(content, replacements) {
  return Object.entries(replacements).reduce(
    (text, [token, value]) => text.replaceAll(token, value),
    content,
  );
}

function chmodIfScript(plan, destination) {
  const relativePath = destination.slice(plan.target.length + 1);
  if (EXECUTABLE.has(relativePath)) chmodSync(destination, 0o755);
}

function isExpectedClaudeSymlink(destination) {
  const stat = lstatSync(destination);
  return stat.isSymbolicLink() && readlinkSync(destination) === "AGENTS.md";
}
