export function createNames(projectName) {
  const packageSlug = toPackageSlug(projectName);
  if (!packageSlug) {
    throw new Error(`Project name "${projectName}" cannot produce a valid npm package scope.`);
  }

  return {
    projectName,
    packageScope: `@${packageSlug}`,
    backendPackage: `@${packageSlug}/backend`,
    webPackage: `@${packageSlug}/web`,
    dbPrefix: packageSlug.replaceAll("-", "_"),
    targetDirName: packageSlug,
  };
}

export function toPackageSlug(input) {
  const normalized = stripAccents(input).toLowerCase();
  const slug = normalized
    .replace(/[^a-z0-9_-]+/g, "-")
    .replace(/[_-]+/g, "-")
    .replace(/^-+|-+$/g, "");

  if (!slug) return "";
  return /^[0-9]/.test(slug) ? `app-${slug}` : slug;
}

function stripAccents(input) {
  return input.normalize("NFD").replace(/[\u0300-\u036f]/g, "");
}
