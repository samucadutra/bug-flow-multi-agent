import { expect, test } from "@playwright/test";
import { alertOf, blockApi, recordedRequests, resetStandIn, setScenario } from "./helpers";

test.beforeEach(async () => {
  await resetStandIn();
});

test("shows total, groups, runs and fetches once", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
  await expect(page.getByText("Total bugs:")).toContainText("20");
  const status = page.getByRole("region", { name: "By status" }).getByRole("listitem");
  await expect(status).toHaveText(["Open17", "Processing1", "Processed2", "Failed0"]);
  const severity = page.getByRole("region", { name: "By severity" }).getByRole("listitem");
  await expect(severity).toHaveText(["Critical0", "Major1", "Minor1"]);
  const rows = page.getByRole("region", { name: "Recent runs" }).getByRole("listitem");
  await expect(rows).toHaveCount(10);
  await expect(rows.nth(0)).toContainText("—");
  await expect(rows.nth(1)).toContainText("1 m 2 s");
  await expect(rows.nth(2)).toContainText("41 s");
  await expect(rows.nth(0).getByRole("link")).toHaveAttribute("href", "/runs/21");
  const requests = await recordedRequests();
  const runRequests = requests.filter((entry) => entry.path === "/api/v1/runs");
  expect(runRequests).toHaveLength(1);
  expect(runRequests[0].query.limit).toBe("10");
  expect(requests.filter((entry) => entry.path === "/api/v1/meta/enums")).toHaveLength(1);
});

test("fetches again on every visit and requests enums once", async ({ page }) => {
  await setScenario("stats-changes");
  await page.goto("/");
  await expect(page.getByText("Total bugs:")).toContainText("20");
  await setScenario("empty");
  const nav = page.getByRole("navigation", { name: "Primary" });
  await nav.getByRole("link", { name: "Bugs" }).click();
  await expect(page.getByRole("heading", { name: "Bugs" })).toBeVisible();
  await nav.getByRole("link", { name: "Dashboard" }).click();
  await expect(page.getByText(/No bugs yet\./)).toBeVisible();
  const requests = await recordedRequests();
  expect(requests.filter((entry) => entry.path === "/api/v1/stats")).toHaveLength(2);
  expect(requests.filter((entry) => entry.path === "/api/v1/meta/enums")).toHaveLength(1);
});

test("shows the loading state while data is pending", async ({ page }) => {
  await setScenario("slow");
  await page.goto("/");
  await expect(page.getByRole("status")).toHaveText("Loading");
  await expect(alertOf(page)).toHaveCount(0);
  await expect(page.getByText("Total bugs:")).toHaveCount(0);
  await expect(page.getByText("Total bugs:")).toBeVisible({ timeout: 10_000 });
  await expect(page.getByRole("status")).toHaveCount(0);
});

test("empty database shows the empty state with an Operations link", async ({ page }) => {
  await setScenario("empty");
  await page.goto("/");
  const message = page.getByText(/No bugs yet\./);
  await expect(message).toHaveText("No bugs yet. Go to Operations to initialize and seed the database.");
  await expect(message.getByRole("link", { name: "Operations" })).toHaveAttribute("href", "/operations");
  await expect(page.getByRole("region", { name: "By status" })).toHaveCount(0);
  await expect(page.getByText("No runs yet.")).toBeVisible();
});

test("API down shows an error with Retry that recovers", async ({ page }) => {
  await blockApi(page);
  await page.goto("/");
  const banner = alertOf(page);
  await expect(banner).toContainText("Cannot reach the BugFlow API");
  const retry = banner.getByRole("button", { name: "Retry" });
  await expect(retry).toBeEnabled();
  await retry.click();
  await expect(banner).toBeVisible();
  await expect(retry).toBeEnabled();
  await page.unrouteAll();
  await page.reload();
  await expect(page.getByText("Total bugs:")).toContainText("20");
});

test("Retry recovers when the API returns", async ({ page }) => {
  await blockApi(page);
  await page.goto("/");
  await expect(alertOf(page)).toBeVisible();
  await page.unrouteAll();
  await page.getByRole("button", { name: "Retry" }).click();
  await expect(alertOf(page)).toHaveCount(0);
  await expect(page.getByText("Total bugs:")).toContainText("20");
});

for (const [scenario, text] of [
  ["unavailable", "Database is unavailable"],
  ["runs-error", "Internal server error"],
  ["enums-unavailable", "Database is unavailable"],
] as const) {
  test(`scenario ${scenario} shows an error banner with Retry`, async ({ page }) => {
    await setScenario(scenario);
    await page.goto("/");
    await expect(alertOf(page)).toContainText(text);
    await expect(page.getByRole("button", { name: "Retry" })).toBeVisible();
    await expect(page.getByRole("region", { name: "By status" })).toHaveCount(0);
  });
}

test("labels follow the API response", async ({ page }) => {
  await setScenario("custom-labels");
  await page.goto("/");
  await expect(page.getByRole("region", { name: "By status" })).toContainText("Awaiting triage");
  await expect(page.getByRole("region", { name: "By component" })).toContainText("Interface and UX");
  const run19 = page.locator('[data-run-id="19"]');
  await expect(run19).toContainText("Agent triage");
});

test.describe("phone viewport", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("runs stay inside the viewport width", async ({ page }) => {
    await page.goto("/");
    const rows = page.getByRole("region", { name: "Recent runs" }).getByRole("listitem");
    await expect(rows).toHaveCount(10);
    for (const row of await rows.all()) {
      const box = await row.boundingBox();
      expect(box).not.toBeNull();
      expect(box!.x).toBeGreaterThanOrEqual(0);
      expect(box!.x + box!.width).toBeLessThanOrEqual(375);
    }
    await expect(page.getByRole("region", { name: "By severity" })).toBeVisible();
  });

  test("the error banner fits the screen", async ({ page }) => {
    await blockApi(page);
    await page.goto("/");
    const banner = alertOf(page);
    await expect(banner).toBeVisible();
    const box = (await banner.boundingBox())!;
    expect(box.x + box.width).toBeLessThanOrEqual(375);
    const scroll = await page.evaluate(() => document.documentElement.scrollWidth);
    expect(scroll).toBeLessThanOrEqual(375);
  });
});
