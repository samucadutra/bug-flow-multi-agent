#!/usr/bin/env node
import { parseArgs } from "./scaffold/args.mjs";
import { collectOptions } from "./scaffold/wizard.mjs";
import { createScaffoldPlan } from "./scaffold/plan.mjs";
import { printDryRun } from "./scaffold/dry-run.mjs";
import { runScaffoldPlan } from "./scaffold/runner.mjs";

async function main() {
  const parsed = parseArgs(process.argv.slice(2));
  const options = await collectOptions(parsed);
  const plan = createScaffoldPlan(options);

  if (options.dryRun) {
    printDryRun(plan);
    return;
  }

  await runScaffoldPlan(plan);
}

main().catch((error) => {
  console.error(`[scaffold] ${error instanceof Error ? error.message : String(error)}`);
  process.exit(1);
});
