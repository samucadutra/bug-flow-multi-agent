import { readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

export function listTemplateFiles(plan) {
  return plan.groups.flatMap((group) => filesForGroup(plan, group));
}

export function filesForGroup(plan, group) {
  const base = join(plan.templateDir, group);
  return walk(base).map((file) => destinationFor(group, relative(base, file)));
}

export function destinationFor(group, relativePath) {
  if (group === "root" || group === "root-db") return relativePath;
  if (group === "backend") return join("apps/backend", relativePath);
  if (group === "backend-db") return join("apps/backend", relativePath);
  if (group === "web-overlay") return join("apps/web", relativePath);
  if (group === "health-db" || group === "health-no-db") {
    return join("apps/backend/src/usecase/health", relativePath);
  }
  return join("apps/backend/src/usecase/health", relativePath);
}

export function walk(dir) {
  return readdirSync(dir).flatMap((name) => {
    const full = join(dir, name);
    return statSync(full).isDirectory() ? walk(full) : [full];
  });
}
