import { afterEach, describe, expect, it, vi } from "vitest";

async function loadConfig() {
  vi.resetModules();
  return import("@/lib/config");
}

afterEach(() => {
  vi.unstubAllEnvs();
});

describe("config", () => {
  it("uses the default when the variable is unset", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "");
    const config = await loadConfig();
    expect(config.apiBaseUrl).toBe("http://localhost:8000/api/v1");
  });

  it("test_base_url_trailing_slash_removed", async () => {
    vi.stubEnv("NEXT_PUBLIC_API_BASE_URL", "http://127.0.0.1:8100/api/v1///");
    const config = await loadConfig();
    expect(config.apiBaseUrl).toBe("http://127.0.0.1:8100/api/v1");
  });

  it("normalizes values directly", async () => {
    const config = await loadConfig();
    expect(config.normalizeBaseUrl(undefined)).toBe(config.DEFAULT_API_BASE_URL);
    expect(config.normalizeBaseUrl("http://x/api/v1/")).toBe("http://x/api/v1");
  });
});
