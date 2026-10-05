import type { GetHealthUseCase } from "@/usecase/health/get-health.usecase";
import type { HttpRequest, HttpResponse } from "@/infra/http/types";

export class GetHealthHandler {
  constructor(private readonly getHealth: GetHealthUseCase) {}

  async handle(_req: HttpRequest): Promise<HttpResponse> {
    const output = await this.getHealth.execute({});
    return { status: output.status === "ok" ? 200 : 503, body: output };
  }
}
