import type { GetHelloUseCase } from "@/usecase/hello/get-hello.usecase";
import type { HttpRequest, HttpResponse } from "@/infra/http/types";

export class GetHelloHandler {
  constructor(private readonly getHello: GetHelloUseCase) {}

  async handle(_req: HttpRequest): Promise<HttpResponse> {
    const output = await this.getHello.execute({});
    return { status: 200, body: output };
  }
}
