const DEFAULT_BACKEND_URL = "http://localhost:4000";

export async function getHelloMessage(): Promise<string> {
  const baseUrl = process.env["BACKEND_INTERNAL_URL"] ?? DEFAULT_BACKEND_URL;
  const response = await fetch(`${baseUrl}/api/hello`, { cache: "no-store" });

  if (!response.ok) return "Backend is not ready";
  const body = await response.json() as { message?: unknown };
  return typeof body.message === "string" ? body.message : "Unexpected backend response";
}
