import { describe, expect, it } from "vitest";
import { GetHealthUseCase } from "./get-health.usecase";

describe("GetHealthUseCase", () => {
  it("returns ok when no database is configured", async () => {
    const useCase = new GetHealthUseCase();

    await expect(useCase.execute({})).resolves.toEqual({ status: "ok" });
  });
});
