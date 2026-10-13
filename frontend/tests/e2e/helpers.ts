import type { Page } from "@playwright/test";

export const STAND_IN = "http://127.0.0.1:8100";

export async function resetStandIn(scenario = "populated") {
  await fetch(`${STAND_IN}/_control/reset`, { method: "POST" });
  if (scenario !== "populated") {
    await fetch(`${STAND_IN}/_control/scenario?name=${scenario}`, { method: "POST" });
  }
}

export async function setScenario(name: string) {
  await fetch(`${STAND_IN}/_control/scenario?name=${name}`, { method: "POST" });
}

export async function recordedRequests(): Promise<{ method: string; path: string; query: Record<string, string> }[]> {
  const response = await fetch(`${STAND_IN}/_control/requests`);
  return (await response.json()).requests;
}

/** Make the browser see the API as unreachable. */
export async function blockApi(page: Page) {
  await page.route(`${STAND_IN}/api/**`, (route) => route.abort("connectionrefused"));
}

/** The page banner; Next.js adds its own route announcer with role alert outside the main area. */
export function alertOf(page: Page) {
  return page.locator("main").getByRole("alert");
}
