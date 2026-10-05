import type { GetHealthInput, GetHealthOutput } from "./get-health.dto";

export class GetHealthUseCase {
  execute(_input: GetHealthInput): Promise<GetHealthOutput> {
    return Promise.resolve({ status: "ok" });
  }
}
