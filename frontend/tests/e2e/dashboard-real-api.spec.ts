import { expect, test } from "@playwright/test";

// Runs against the real F09 API on 127.0.0.1:8000 with the seeded sample data:
//   E2E_TARGET=real npm run test:e2e
const API = "http://127.0.0.1:8000/api/v1";

test("counts, runs and labels equal the API values", async ({ page, request }) => {
  const stats = await (await request.get(`${API}/stats`)).json();
  const runs = await (await request.get(`${API}/runs?limit=10`)).json();
  const enums = await (await request.get(`${API}/meta/enums`)).json();
  const labelOf = (name: string, code: string) =>
    enums.enums.find((entry: { name: string }) => entry.name === name).values.find((v: { code: string }) => v.code === code)
      .label as string;

  await page.goto("/");
  await expect(page.getByText("Total bugs:")).toContainText(String(stats.total));

  const groups = [
    ["By status", "BugStatus", stats.by_status],
    ["By component", "Component", stats.by_component],
    ["By severity", "Severity", stats.by_severity],
  ] as const;
  for (const [title, enumName, counts] of groups) {
    const items = page.getByRole("region", { name: title }).getByRole("listitem");
    const expected = (enums.enums.find((e: { name: string }) => e.name === enumName).values as { code: string }[]).map(
      (v) => `${labelOf(enumName, v.code)}${counts[v.code] ?? 0}`,
    );
    await expect(items).toHaveText(expected);
  }

  const rows = page.getByRole("region", { name: "Recent runs" }).getByRole("listitem");
  await expect(rows).toHaveCount(runs.items.length);
  const ids = await rows.evaluateAll((nodes) => nodes.map((node) => Number(node.getAttribute("data-run-id"))));
  expect(ids).toEqual(runs.items.map((run: { id: number }) => run.id));
  for (const [index, run] of runs.items.entries()) {
    await expect(rows.nth(index)).toContainText(labelOf("RunType", run.type));
    await expect(rows.nth(index)).toContainText(labelOf("RunStatus", run.status));
  }
});
