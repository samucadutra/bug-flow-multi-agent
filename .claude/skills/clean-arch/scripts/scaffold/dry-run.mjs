import { listTemplateFiles } from "./templates.mjs";

export function printDryRun(plan) {
  console.log(`Target: ${plan.target}`);
  console.log("\nWould create:");
  for (const file of listTemplateFiles(plan)) {
    console.log(`  ${file}`);
  }
  console.log("  CLAUDE.md -> AGENTS.md");

  console.log("\nWould run:");
  for (const command of plan.commands) {
    console.log(`  ${command.command} ${command.args.join(" ")}`);
  }
}
