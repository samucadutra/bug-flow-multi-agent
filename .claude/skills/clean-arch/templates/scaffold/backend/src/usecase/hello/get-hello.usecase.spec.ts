import { describe, expect, it } from "vitest";
import { GetHelloUseCase } from "./get-hello.usecase";

describe("GetHelloUseCase", () => {
  it("returns the hello world message", async () => {
    const useCase = new GetHelloUseCase();

    await expect(useCase.execute({})).resolves.toEqual({ message: "Hello World" });
  });
});
