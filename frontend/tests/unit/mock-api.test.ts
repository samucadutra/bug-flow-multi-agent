import { afterAll, beforeAll, beforeEach, describe, expect, it } from "vitest";
import { createMockApi, type MockApi } from "../mocks/mock-api.mjs";

let api: MockApi;
let base: string;

async function get(path: string) {
  return fetch(`${base}${path}`);
}

async function control(path: string, method = "GET") {
  const response = await fetch(`${base}/_control/${path}`, { method });
  return response.json();
}

beforeAll(async () => {
  api = createMockApi({ port: 0 });
  base = `http://127.0.0.1:${await api.start()}`;
});

afterAll(async () => {
  await api.stop();
});

beforeEach(async () => {
  await control("reset", "POST");
});

describe("mock api", () => {
  it("serves the populated scenario and honours the runs limit", async () => {
    const stats = await (await get("/api/v1/stats")).json();
    expect(stats.total).toBe(20);
    const runs = await (await get("/api/v1/runs?limit=10")).json();
    expect(runs.items).toHaveLength(10);
    expect(runs.items[0].id).toBe(21);
  });

  it("records requests but not control calls or preflights", async () => {
    await get("/api/v1/stats");
    await fetch(`${base}/api/v1/stats`, { method: "OPTIONS" });
    const record = await control("requests");
    expect(record.requests).toHaveLength(1);
    expect(record.requests[0]).toMatchObject({ method: "GET", path: "/api/v1/stats" });
  });

  it("switches scenarios and answers errors", async () => {
    await control("scenario?name=empty", "POST");
    expect((await (await get("/api/v1/stats")).json()).total).toBe(0);
    await control("scenario?name=unavailable", "POST");
    const response = await get("/api/v1/stats");
    expect(response.status).toBe(503);
    expect((await response.json()).error.message).toBe("Database is unavailable");
    await control("scenario?name=runs-error", "POST");
    expect((await get("/api/v1/runs")).status).toBe(500);
    expect((await get("/api/v1/bugs/999999")).status).toBe(404);
  });

  it("allows the frontend origin through CORS", async () => {
    const response = await fetch(`${base}/api/v1/stats`, {
      headers: { Origin: "http://localhost:3000" },
    });
    expect(response.headers.get("access-control-allow-origin")).toBe("http://localhost:3000");
  });

  it("plays the scripted run over time and in the event stream", async () => {
    const first = await (await get("/api/v1/runs/8")).json();
    expect(first.steps[0].status).toBe("running");
    expect(first.run.status).toBe("running");
    const stream = await (await get("/api/v1/runs/7/events")).text();
    const frames = stream.split("\n\n").filter(Boolean);
    expect(frames).toHaveLength(10);
    expect(frames[frames.length - 1]).toContain("event: run");
    await new Promise((resolve) => setTimeout(resolve, 2100));
    const done = await (await get("/api/v1/runs/8")).json();
    expect(done.run.status).toBe("succeeded");
    expect(done.steps).toHaveLength(5);
  });
});
