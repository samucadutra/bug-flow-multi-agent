import { describe, expect, it } from "vitest";
import { buildFastifyServer } from "./fastify-server";
import type { HttpRoute } from "./types";

describe("buildFastifyServer", () => {
  it("serves registered routes", async () => {
    const app = buildFastifyServer({
      logger: { level: "error" },
      routes: [route("GET", "/api/hello", { message: "Hello World" })],
    });

    const response = await app.inject({ method: "GET", url: "/api/hello" });

    expect(response.statusCode).toBe(200);
    expect(response.json()).toEqual({ message: "Hello World" });
  });

  it("returns 404 for missing routes", async () => {
    const app = buildFastifyServer({ logger: { level: "error" }, routes: [] });

    const response = await app.inject({ method: "GET", url: "/missing" });

    expect(response.statusCode).toBe(404);
  });
});

function route(method: "GET", path: string, body: unknown): HttpRoute {
  return {
    method,
    path,
    handler: { handle: () => Promise.resolve({ status: 200, body }) },
  };
}
