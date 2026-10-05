import type { GetHelloInput, GetHelloOutput } from "./get-hello.dto";

export class GetHelloUseCase {
  execute(_input: GetHelloInput): Promise<GetHelloOutput> {
    return Promise.resolve({ message: "Hello World" });
  }
}
