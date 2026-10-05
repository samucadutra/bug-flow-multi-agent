import { spawnSync } from "node:child_process";

export function runCommand(plan, command) {
  console.log(`[scaffold] ${command.label}...`);
  const result = spawnSync(command.command, command.args, {
    cwd: plan.target,
    stdio: "inherit",
    shell: false,
  });

  if (result.error) throw new Error(`${command.label} failed: ${result.error.message}`);
  if (result.status !== 0) throw new Error(`${command.label} exited ${result.status}.`);
}
