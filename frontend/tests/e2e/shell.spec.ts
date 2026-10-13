import { expect, test } from "@playwright/test";
import { resetStandIn } from "./helpers";

test.beforeEach(async () => {
  await resetStandIn();
});

test("primary navigation lists four links and marks the current page", async ({ page }) => {
  await page.goto("/");
  const nav = page.getByRole("navigation", { name: "Primary" });
  await expect(nav.getByRole("link")).toHaveText(["Dashboard", "Bugs", "Search", "Operations"]);
  await expect(nav.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
  await expect(page.getByRole("banner").getByText("BugFlow")).toBeVisible();
});

for (const [name, route] of [
  ["Bugs", "/bugs"],
  ["Search", "/search"],
  ["Operations", "/operations"],
] as const) {
  test(`${name} link opens ${route}`, async ({ page }) => {
    await page.goto("/");
    await page.getByRole("navigation", { name: "Primary" }).getByRole("link", { name }).click();
    await expect(page).toHaveURL(new RegExp(`${route}$`));
    await expect(page.getByRole("link", { name, exact: true })).toHaveAttribute("aria-current", "page");
    await expect(page.getByRole("heading", { name, level: 1 })).toBeVisible();
    await expect(page.locator("main [role=alert]")).toHaveCount(0);
  });
}

test("an unknown route keeps the shell", async ({ page }) => {
  await page.goto("/does-not-exist");
  await expect(page.getByRole("navigation", { name: "Primary" }).getByRole("link")).toHaveCount(4);
  await expect(page.getByRole("main")).toContainText("was not found");
  await page.getByRole("main").getByRole("link", { name: /Dashboard/ }).click();
  await expect(page).toHaveURL(/localhost:3000\/$/);
});

test.describe("phone viewport", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("test_mobile_nav_toggle", async ({ page }) => {
    await page.goto("/");
    const button = page.getByRole("button", { name: "Menu" });
    const links = page.getByRole("navigation", { name: "Primary" }).getByRole("link");
    await expect(button).toBeVisible();
    await expect(button).toHaveAttribute("aria-expanded", "false");
    await expect(links.first()).toBeHidden();
    await button.click();
    await expect(button).toHaveAttribute("aria-expanded", "true");
    await expect(links).toHaveCount(4);
    for (const link of await links.all()) await expect(link).toBeVisible();
    await links.nth(1).click();
    await expect(page).toHaveURL(/\/bugs$/);
    await expect(button).toHaveAttribute("aria-expanded", "false");
  });

  test("test_no_horizontal_scroll_375", async ({ page }) => {
    await page.goto("/");
    await expect(page.getByRole("heading", { name: "Dashboard" })).toBeVisible();
    await expect(page.getByText("Total bugs:")).toBeVisible();
    const widths = await page.evaluate(() => ({
      scroll: document.documentElement.scrollWidth,
      client: document.documentElement.clientWidth,
    }));
    expect(widths.scroll).toBeLessThanOrEqual(375);
    expect(widths.client).toBeLessThanOrEqual(375);
  });
});
