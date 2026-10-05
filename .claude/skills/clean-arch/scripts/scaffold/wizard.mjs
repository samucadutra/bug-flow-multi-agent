import readline from "node:readline";
import { existsSync, readdirSync } from "node:fs";
import { resolve } from "node:path";
import { createInterface } from "node:readline/promises";
import { stdin as input, stdout as output } from "node:process";
import { defaultsFor, SHAPES } from "./defaults.mjs";
import { createNames } from "./naming.mjs";

export async function collectOptions(parsed) {
  if (parsed.yes) return completeWithDefaults(parsed);
  if (!process.stdin.isTTY) return completeForNonInteractive(parsed);

  const options = await askMissingOptions(parsed);
  const confirmed = await confirm(summaryFor(options), true);

  if (!confirmed) {
    console.log("Scaffold cancelled.");
    process.exit(0);
  }
  return options;
}

function completeWithDefaults(parsed) {
  const defaults = defaultsFor(parsed);
  return normalizeOptions({ ...defaults, ...parsed });
}

function completeForNonInteractive(parsed) {
  if (!parsed.projectName) throw new Error("Project name is required outside the wizard.");
  return completeWithDefaults({ yes: true, ...parsed });
}

async function askMissingOptions(parsed) {
  const defaults = defaultsFor(parsed);
  const projectName = parsed.projectName ?? await text("Project name:", "clean-arch-app");
  const target = parsed.target ?? await askTargetMode();
  const force = parsed.force ?? await askForceIfTargetIsNotEmpty(projectName, target);

  return normalizeOptions({
    projectName,
    shape: parsed.shape ?? await askShape(defaults.shape),
    db: parsed.db ?? await confirm("Enable PostgreSQL/Prisma?", defaults.db),
    install: parsed.install ?? await confirm("Install dependencies?", defaults.install),
    gates: parsed.gates ?? await confirm("Run gates after scaffold?", defaults.gates),
    git: parsed.git ?? await confirm("Initialize git?", defaults.git),
    target,
    dryRun: parsed.dryRun,
    force,
  });
}

async function askTargetMode() {
  return select("Where should I create the project?", [
    { name: "New folder named after the project", value: undefined },
    { name: "Current folder", value: "." },
  ], undefined);
}

async function askForceIfTargetIsNotEmpty(projectName, target) {
  const targetDir = resolveTarget(projectName, target);
  if (!existsSync(targetDir) || readdirSync(targetDir).length === 0) return false;

  const shouldContinue = await confirm([
    "Target folder is not empty.",
    "Add missing scaffold files without overwriting existing files?",
  ].join("\n"), true);

  if (!shouldContinue) {
    console.log("Scaffold cancelled.");
    process.exit(0);
  }
  return true;
}

function resolveTarget(projectName, target) {
  if (target) return resolve(process.cwd(), target);
  return resolve(process.cwd(), createNames(projectName).targetDirName);
}

async function askShape(defaultShape) {
  return select("Project shape:", [
    { name: "Backend only", value: SHAPES.backend },
    { name: "Backend + Next.js", value: SHAPES.backendNext },
  ], defaultShape);
}

async function text(message, defaultValue) {
  const rl = createInterface({ input, output });
  const answer = await rl.question(`${message} (${defaultValue}) `);
  rl.close();
  return (answer ?? "").trim() || defaultValue;
}

async function confirm(message, defaultValue) {
  const yes = { name: "Yes", value: true };
  const no = { name: "No", value: false };
  const choices = defaultValue ? [yes, no] : [no, yes];
  return select(message, choices, defaultValue);
}

async function select(message, choices, defaultValue) {
  const active = choices.findIndex((choice) => choice.value === defaultValue);
  const initialIndex = active >= 0 ? active : 0;
  return selectWithKeys(message, choices, initialIndex);
}

async function selectWithKeys(message, choices, initialIndex) {
  readline.emitKeypressEvents(input);
  input.setRawMode(true);
  input.resume();
  output.write("\x1B[?25l");

  let index = initialIndex;
  let renderedLines = 0;

  return new Promise((resolve) => {
    const finish = (value) => {
      input.off("keypress", onKeypress);
      input.setRawMode(false);
      input.pause();
      output.write("\x1B[?25h\n");
      resolve(value);
    };

    const onKeypress = (str, key) => {
      if (key.ctrl && key.name === "c") process.exit(130);
      if (key.name === "up") index = (index - 1 + choices.length) % choices.length;
      if (key.name === "down") index = (index + 1) % choices.length;
      if (isReturnKey(str, key)) finish(choices[index].value);
      if (!isReturnKey(str, key)) renderedLines = renderSelect(message, choices, index, renderedLines);
    };

    input.on("keypress", onKeypress);
    renderedLines = renderSelect(message, choices, index, renderedLines);
  });
}

function isReturnKey(str, key) {
  return key.name === "return" || key.name === "enter" || str === "\r" || str === "\n";
}

function renderSelect(message, choices, activeIndex, previousLines) {
  if (previousLines > 0) output.write(`\x1B[${previousLines}F`);

  const lines = [
    ...message.split("\n"),
    ...choices.map((choice, index) => `${index === activeIndex ? "●" : "○"} ${choice.name}`),
  ];

  for (const line of lines) output.write(`\x1B[2K${line}\n`);
  return lines.length;
}

function normalizeOptions(options) {
  if (!options.projectName?.trim()) throw new Error("Project name is required.");
  return {
    ...options,
    projectName: options.projectName.trim(),
    shape: options.shape,
    db: Boolean(options.db),
    install: options.install !== false,
    gates: options.gates !== false,
    git: options.git !== false,
    dryRun: Boolean(options.dryRun),
    force: Boolean(options.force),
  };
}

function summaryFor(options) {
  return [
    "Create project?",
    `  name: ${options.projectName}`,
    `  target: ${options.target ?? `./${options.projectName}`}`,
    `  shape: ${options.shape}`,
    `  database: ${options.db ? "yes" : "no"}`,
    `  install: ${options.install ? "yes" : "no"}`,
    `  gates: ${options.gates ? "yes" : "no"}`,
    `  git: ${options.git ? "yes" : "no"}`,
  ].join("\n");
}
