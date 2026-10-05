import { describe, expect, it } from "vitest";
import type { DatabaseHealthGateway } from "@/domain/health/database-health.gateway";
import { GetHealthUseCase } from "./get-health.usecase";

describe("GetHealthUseCase", () => {
  it("returns ok when database is reachable", async () => {
    const useCase = new GetHealthUseCase(new FakeDatabaseHealthGateway("ok"));

    await expect(useCase.execute({})).resolves.toEqual({ status: "ok", db: "ok" });
  });

  it("returns degraded when database is unreachable", async () => {
    const useCase = new GetHealthUseCase(new FakeDatabaseHealthGateway("unreachable"));

    await expect(useCase.execute({})).resolves.toEqual({
      status: "degraded",
      db: "unreachable",
    });
  });
});

class FakeDatabaseHealthGateway implements DatabaseHealthGateway {
  constructor(private readonly result: "ok" | "unreachable") {}

  check(): Promise<"ok" | "unreachable"> {
    return Promise.resolve(this.result);
  }
}
