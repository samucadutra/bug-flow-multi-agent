import type { DatabaseHealthGateway } from "@/domain/health/database-health.gateway";
import type { GetHealthInput, GetHealthOutput } from "./get-health.dto";

export class GetHealthUseCase {
  constructor(private readonly databaseHealth: DatabaseHealthGateway) {}

  async execute(_input: GetHealthInput): Promise<GetHealthOutput> {
    const db = await this.databaseHealth.check();
    return { status: db === "ok" ? "ok" : "degraded", db };
  }
}
