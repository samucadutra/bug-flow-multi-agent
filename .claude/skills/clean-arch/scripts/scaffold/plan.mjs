import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";
import { createNames } from "./naming.mjs";

const SKILL_DIR = resolve(dirname(fileURLToPath(import.meta.url)), "../..");
const TEMPLATE_DIR = resolve(SKILL_DIR, "templates/scaffold");

export function createScaffoldPlan(options) {
  const names = createNames(options.projectName);
  const target = resolveTarget(options, names);
  const web = options.shape === "backend-n-nextjs";

  return {
    options,
    names,
    target,
    web,
    db: options.db,
    templateDir: TEMPLATE_DIR,
    replacements: createReplacements(options, names, web),
    groups: createTemplateGroups(options, web),
    commands: createCommands(options, names, web),
  };
}

function resolveTarget(options, names) {
  if (options.target) return resolve(process.cwd(), options.target);
  return resolve(process.cwd(), names.targetDirName);
}

function createReplacements(options, names, web) {
  return {
    __PROJECT_NAME__: options.projectName,
    __ROOT_PACKAGE_NAME__: names.targetDirName,
    __PACKAGE_SCOPE__: names.packageScope,
    __BACKEND_PACKAGE__: names.backendPackage,
    __WEB_PACKAGE__: names.webPackage,
    __DB_NAME_PREFIX__: names.dbPrefix,
    __HAS_DB__: String(options.db),
    __HAS_WEB__: String(web),
    __WEB_WORKSPACE_ENTRY__: web ? ',\n    "apps/web"' : "",
    __WEB_DEV_SCRIPT__: web ? `,\n    "dev:web": "npm --workspace ${names.webPackage} run dev"` : "",
    __BUILD_SCRIPT__: web
      ? `npm --workspace ${names.webPackage} run build && npm --workspace ${names.backendPackage} run build`
      : `npm --workspace ${names.backendPackage} run build`,
    __LINT_SCRIPT__: web
      ? `npm --workspace ${names.webPackage} run lint && npm --workspace ${names.backendPackage} run lint`
      : `npm --workspace ${names.backendPackage} run lint`,
    __TYPECHECK_SCRIPT__: web
      ? `npm --workspace ${names.webPackage} run typecheck && npm --workspace ${names.backendPackage} run typecheck`
      : `npm --workspace ${names.backendPackage} run typecheck`,
    __AGENTS_CLEAN_TEXT__: options.db
      ? "It drops the branch database when DB support is enabled."
      : "It stops dev processes and removes stale pid files.",
    __README_DB_SECTION__: options.db ? databaseReadmeSection() : "",
    __README_WEB_SECTION__: web ? webReadmeSection() : "",
    __BACKEND_PRISMA_SCRIPTS__: options.db
      ? ',\n    "prisma:generate": "prisma generate --allow-no-models",\n    "prisma:migrate": "prisma migrate deploy",\n    "prisma:migrate:dev": "prisma migrate dev"'
      : "",
    __BACKEND_PRISMA_DEP__: options.db ? ',\n    "@prisma/client": "^5"' : "",
    __BACKEND_PRISMA_DEV_DEP__: options.db ? ',\n    "prisma": "^5"' : "",
    __KNIP_PRISMA_IGNORE_BINARY__: options.db ? ', "prisma"' : "",
    __KNIP_PRISMA_IGNORE_DEP__: options.db ? ', "prisma"' : "",
  };
}

function createTemplateGroups(options, web) {
  const groups = ["root", "backend"];
  if (options.db) groups.push("root-db", "backend-db");
  groups.push(options.db ? "health-db" : "health-no-db");
  if (web) groups.push("web-overlay");
  return groups;
}

function createCommands(options, names, web) {
  const commands = [];
  if (web) commands.push(createNextCommand());
  if (options.git) commands.push(["git", ["init"], "Initialize git"]);
  if (options.git) commands.push(["git", ["branch", "-M", "main"], "Set main branch"]);
  if (options.install) {
    commands.push(["npm", ["install", "--no-audit", "--no-fund"], "Install dependencies"]);
  }
  if (options.db && options.install) {
    commands.push(["npm", ["--workspace", names.backendPackage, "run", "prisma:generate"], "Generate Prisma client"]);
  }
  if (options.gates) commands.push(["node", ["scripts/run-gates.mjs"], "Run clean-arch gates"]);
  return commands.map(([command, args, label]) => ({ command, args, label, cwd: undefined }));
}

function createNextCommand() {
  return [
    "npx",
    [
      "--yes",
      "create-next-app@latest",
      "apps/web",
      "--yes",
      "--ts",
      "--eslint",
      "--tailwind",
      "--app",
      "--no-src-dir",
      "--import-alias",
      "@/*",
      "--use-npm",
      "--skip-install",
      "--disable-git",
    ],
    "Create Next.js app",
  ];
}

function databaseReadmeSection() {
  return [
    "\n## Database",
    "",
    "This project uses PostgreSQL and Prisma.",
    "",
    "After editing `apps/backend/prisma/schema.prisma`, create a migration with:",
    "",
    "```bash",
    "./scripts/migrate-dev.sh -- --name <change>",
    "```",
  ].join("\n");
}

function webReadmeSection() {
  return [
    "\n## Web",
    "",
    "When generated with Next.js, `./scripts/init.sh` starts both backend and web.",
    "The web app calls the backend server-side through `BACKEND_INTERNAL_URL`.",
  ].join("\n");
}
