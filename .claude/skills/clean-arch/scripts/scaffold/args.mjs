const FLAGS_WITH_VALUE = new Set(["--shape", "--target"]);

const FLAG_ALIASES = new Map([
  ["--database", "--db"],
  ["--with-db", "--db"],
]);

export function parseArgs(argv) {
  const parsed = { projectName: undefined };

  for (let index = 0; index < argv.length; index += 1) {
    const token = argv[index];
    if (!token.startsWith("--")) {
      parsed.projectName ??= token;
      continue;
    }
    index = parseFlag(argv, parsed, index);
  }

  return parsed;
}

function parseFlag(argv, parsed, index) {
  const token = normalizeAlias(argv[index]);
  const [flag, inlineValue] = token.split("=", 2);
  const value = inlineValue ?? readValue(argv, index, flag);

  assignFlag(parsed, flag, value);
  return inlineValue === undefined && FLAGS_WITH_VALUE.has(flag) ? index + 1 : index;
}

function normalizeAlias(token) {
  const [flag, value] = token.split("=", 2);
  const normalized = FLAG_ALIASES.get(flag) ?? flag;
  return value === undefined ? normalized : `${normalized}=${value}`;
}

function readValue(argv, index, flag) {
  if (!FLAGS_WITH_VALUE.has(flag)) return undefined;
  const value = argv[index + 1];
  if (!value || value.startsWith("--")) throw new Error(`Missing value for ${flag}.`);
  return value;
}

function assignFlag(parsed, flag, value) {
  if (flag === "--shape") parsed.shape = normalizeShape(value);
  else if (flag === "--target") parsed.target = value;
  else if (flag === "--db") parsed.db = true;
  else if (flag === "--no-db") parsed.db = false;
  else if (flag === "--install") parsed.install = true;
  else if (flag === "--no-install") parsed.install = false;
  else if (flag === "--gates") parsed.gates = true;
  else if (flag === "--no-gates") parsed.gates = false;
  else if (flag === "--git") parsed.git = true;
  else if (flag === "--no-git") parsed.git = false;
  else if (flag === "--yes") parsed.yes = true;
  else if (flag === "--dry-run") parsed.dryRun = true;
  else if (flag === "--force") parsed.force = true;
  else throw new Error(`Unknown flag: ${flag}.`);
}

function normalizeShape(value) {
  if (value === "backend" || value === "backend-n-nextjs") return value;
  if (value === "monorepo" || value === "backend-web") return "backend-n-nextjs";
  throw new Error(`Invalid shape "${value}". Expected backend or backend-n-nextjs.`);
}
