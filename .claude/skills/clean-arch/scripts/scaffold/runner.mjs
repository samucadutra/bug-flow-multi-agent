import { existsSync, mkdirSync, readdirSync } from "node:fs";
import { spawnSync } from "node:child_process";
import { writeClaudeSymlink, writeTemplateGroups } from "./writer.mjs";
import { runCommand } from "./commands.mjs";

export async function runScaffoldPlan(plan) {
  assertSupportedPlatform();
  runPreflight(plan);
  prepareTarget(plan);
  writeTemplateGroups(plan, plan.groups.filter((group) => group !== "web-overlay"));
  writeClaudeSymlink(plan);

  for (const command of plan.commands) {
    runCommand(plan, command);
    if (command.label === "Create Next.js app") {
      writeTemplateGroups(plan, ["web-overlay"], { allowOverwrite: true });
    }
  }

  printNextSteps(plan);
}

function runPreflight(plan) {
  requireCommand("npm");
  if (plan.web) requireCommand("npx");
  if (plan.options.git) requireCommand("git");
}

function requireCommand(command) {
  const result = spawnSync(command, ["--version"], { stdio: "ignore" });
  if (result.status !== 0) throw new Error(`Missing required command: ${command}`);
}

function assertSupportedPlatform() {
  if (process.platform === "win32") {
    throw new Error("Native Windows is not supported yet. Use WSL, macOS, or Linux.");
  }
}

function prepareTarget(plan) {
  if (!existsSync(plan.target)) {
    mkdirSync(plan.target, { recursive: true });
    return;
  }
  if (!plan.options.force && readdirSync(plan.target).length > 0) {
    throw new Error(`Target directory is not empty. Re-run with --force to add missing scaffold files.`);
  }
}

function printNextSteps(plan) {
  console.log("\n[scaffold] Ready.");
  console.log(`  cd ${plan.target}`);
  console.log("  ./scripts/init.sh");
}
