import test from "node:test";
import assert from "node:assert/strict";
import { resolve } from "node:path";
import { createScaffoldPlan } from "../plan.mjs";

test("backend plan omits web and db templates", () => {
  const plan = createScaffoldPlan({ projectName: "demo", shape: "backend", db: false });
  assert.equal(plan.web, false);
  assert.equal(plan.db, false);
  assert.ok(plan.groups.includes("health-no-db"));
  assert.ok(!plan.groups.includes("backend-db"));
});

test("backend and nextjs plan includes web overlay and db templates", () => {
  const plan = createScaffoldPlan({ projectName: "demo", shape: "backend-n-nextjs", db: true });
  assert.equal(plan.web, true);
  assert.equal(plan.db, true);
  assert.ok(plan.groups.includes("web-overlay"));
  assert.ok(plan.groups.includes("backend-db"));
});

test("explicit target current directory is honored", () => {
  const plan = createScaffoldPlan({ projectName: "demo", shape: "backend", db: false, target: "." });

  assert.equal(plan.target, resolve(process.cwd(), "."));
});
