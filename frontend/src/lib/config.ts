/** The only module that reads the process environment. */

export const DEFAULT_API_BASE_URL = "http://localhost:8000/api/v1";

/** Remove trailing slashes; an empty or missing value selects the default. */
export function normalizeBaseUrl(raw: string | undefined): string {
  const trimmed = (raw ?? "").trim().replace(/\/+$/, "");
  return trimmed === "" ? DEFAULT_API_BASE_URL : trimmed;
}

// Next.js inlines this exact expression at build time; do not read the variable dynamically.
export const apiBaseUrl: string = normalizeBaseUrl(process.env.NEXT_PUBLIC_API_BASE_URL);
