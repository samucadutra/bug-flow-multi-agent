import { describe, expect, it } from "vitest";
import { ApiError, createApiClient, type FetchLike } from "@/lib/api";

interface Call {
  url: string;
  init?: RequestInit;
}

function recorder(respond: (url: string) => Response | Promise<Response>) {
  const calls: Call[] = [];
  const fetch: FetchLike = async (url, init) => {
    calls.push({ url, init });
    return respond(url);
  };
  return { calls, fetch };
}

const ok = (body: unknown, status = 200) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

const BASE = "http://127.0.0.1:8100/api/v1";

describe("api client", () => {
  it("test_base_url_trailing_slash_removed", async () => {
    const { calls, fetch } = recorder(() => ok({ total: 0 }));
    await createApiClient({ baseUrl: `${BASE}/`, fetch }).stats();
    expect(calls[0].url).toBe(`${BASE}/stats`);
  });

  it("test_query_omits_undefined_filters", async () => {
    const { calls, fetch } = recorder(() => ok({ items: [] }));
    const client = createApiClient({ baseUrl: BASE, fetch });
    await client.listBugs({ search: "a&b=c", status: undefined });
    expect(new URL(calls[0].url).searchParams.get("search")).toBe("a&b=c");
    expect([...new URL(calls[0].url).searchParams.keys()]).toEqual(["search"]);
    await client.listBugs({ status: "open", component: "backend", page: 2, page_size: 20 });
    expect(calls[1].url).toBe(`${BASE}/bugs?status=open&component=backend&page=2&page_size=20`);
  });

  it("uses the F09 paths for reads", async () => {
    const { calls, fetch } = recorder(() => ok({}));
    const client = createApiClient({ baseUrl: BASE, fetch });
    await client.health();
    await client.enums();
    await client.getBug(1);
    await client.similarBugs(1);
    await client.bugRuns(1);
    await client.getReport(1);
    await client.search("login token", 10);
    await client.listRuns({ limit: 10, type: "triage" });
    await client.getRun(7);
    expect(calls.map((call) => call.url.replace(BASE, ""))).toEqual([
      "/health",
      "/meta/enums",
      "/bugs/1",
      "/bugs/1/similar",
      "/bugs/1/runs",
      "/bugs/1/report?format=json",
      "/search?q=login+token&limit=10",
      "/runs?limit=10&type=triage",
      "/runs/7",
    ]);
  });

  it("sends JSON bodies for writes", async () => {
    const { calls, fetch } = recorder(() => ok({ run_ids: [1] }, 202));
    const client = createApiClient({ baseUrl: BASE, fetch });
    const fields = {
      title: "t",
      description: "d",
      reproduction_steps: "r",
      system_version: "1",
      environment: "testing",
      reporting_team: "qa",
    };
    await client.createBug(fields);
    await client.updateBug(3, { title: "new" });
    await client.reopenBug(3);
    await client.initDb();
    await client.seedDb();
    await client.resetDb();
    await client.indexAll();
    await client.startTriage({ bug_id: 4 });
    await client.startTriage({ all: true });
    const summary = calls.map((call) => [call.init?.method, call.url.replace(BASE, ""), call.init?.body]);
    expect(summary).toEqual([
      ["POST", "/bugs", JSON.stringify(fields)],
      ["PATCH", "/bugs/3", JSON.stringify({ title: "new" })],
      ["POST", "/bugs/3/reopen", JSON.stringify({ confirm: true })],
      ["POST", "/admin/db/init", undefined],
      ["POST", "/admin/db/seed", undefined],
      ["POST", "/admin/db/reset", JSON.stringify({ confirm: true })],
      ["POST", "/admin/index", undefined],
      ["POST", "/triage-runs", JSON.stringify({ bug_id: 4 })],
      ["POST", "/triage-runs", JSON.stringify({ all: true })],
    ]);
    expect(calls[0].init?.headers).toEqual({ "Content-Type": "application/json" });
  });

  it("resolves text report formats as strings", async () => {
    const { calls, fetch } = recorder(() => new Response("# Report"));
    const client = createApiClient({ baseUrl: BASE, fetch });
    expect(await client.getReport(1, "md")).toBe("# Report");
    expect(await client.getReport(1, "html")).toBe("# Report");
    expect(calls.map((call) => new URL(call.url).searchParams.get("format"))).toEqual(["md", "html"]);
  });

  it("test_api_error_from_envelope", async () => {
    const envelope = { error: { code: "not_found", message: "Bug 9 not found", details: [{ field: "id" }] } };
    const { fetch } = recorder(() => ok(envelope, 404));
    const error = await createApiClient({ baseUrl: BASE, fetch }).getBug(9).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error).toMatchObject({
      status: 404,
      code: "not_found",
      message: "Bug 9 not found",
      details: [{ field: "id" }],
    });
  });

  it("preserves validation details", async () => {
    const details = [{ field: "title", message: "must be at most 120 characters" }];
    const { fetch } = recorder(() => ok({ error: { code: "validation_error", message: "Invalid", details } }, 422));
    const error = await createApiClient({ baseUrl: BASE, fetch })
      .createBug({
        title: "x",
        description: "",
        reproduction_steps: "",
        system_version: "",
        environment: "",
        reporting_team: "",
      })
      .catch((e: unknown) => e);
    expect(error).toMatchObject({ status: 422, code: "validation_error", details });
  });

  it("test_network_failure_is_api_error", async () => {
    const fetch: FetchLike = async () => {
      throw new TypeError("fetch failed");
    };
    const error = (await createApiClient({ baseUrl: BASE, fetch }).stats().catch((e: unknown) => e)) as ApiError;
    expect(error).toBeInstanceOf(ApiError);
    expect(error.status).toBe(0);
    expect(error.code).toBe("network_error");
    expect(error.message).toBe(`Cannot reach the BugFlow API at ${BASE}. Check that the server is running.`);
    expect(error.message).not.toContain("fetch failed");
    expect(error.message).not.toMatch(/\n\s+at /);
  });

  it("maps a non-envelope error body to a generic HTTP error", async () => {
    const { fetch } = recorder(() => new Response("Bad gateway raw", { status: 502 }));
    const error = (await createApiClient({ baseUrl: BASE, fetch }).stats().catch((e: unknown) => e)) as ApiError;
    expect(error).toMatchObject({
      status: 502,
      code: "http_error",
      message: "The API returned an unexpected response (HTTP 502).",
    });
  });
});
