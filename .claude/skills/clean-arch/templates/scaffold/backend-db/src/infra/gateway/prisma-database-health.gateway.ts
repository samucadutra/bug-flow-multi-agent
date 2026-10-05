import type { PrismaClient } from "@prisma/client";
import type { DatabaseHealthGateway } from "@/domain/health/database-health.gateway";

export class PrismaDatabaseHealthGateway implements DatabaseHealthGateway {
  constructor(private readonly prisma: PrismaClient) {}

  async check(): Promise<"ok" | "unreachable"> {
    try {
      await this.prisma.$queryRaw`SELECT 1`;
      return "ok";
    } catch (_error) {
      return "unreachable";
    }
  }
}
