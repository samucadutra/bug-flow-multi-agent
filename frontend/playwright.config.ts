import { defineConfig, devices } from "@playwright/test";

const real = process.env.E2E_TARGET === "real";
const standIn = "http://127.0.0.1:8100";
const apiBase = real ? "http://127.0.0.1:8000/api/v1" : `${standIn}/api/v1`;

export default defineConfig({
  testDir: "tests/e2e",
  testMatch: real ? /.*-real-api\.spec\.ts/ : /^(?!.*-real-api).*\.spec\.ts$/,
  fullyParallel: false,
  workers: 1,
  reporter: [["list"]],
  use: {
    baseURL: "http://localhost:3000",
    trace: "retain-on-failure",
    timezoneId: "UTC",
  },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1280, height: 800 } } }],
  webServer: [
    ...(real
      ? []
      : [
          {
            command: "npm run mock:api",
            url: `${standIn}/_control/requests`,
            reuseExistingServer: true,
          },
        ]),
    {
      command: "npm run dev",
      url: "http://localhost:3000",
      reuseExistingServer: true,
      timeout: 120_000,
      env: { NEXT_PUBLIC_API_BASE_URL: apiBase, PORT: "3000", TZ: "UTC" },
    },
  ],
});
