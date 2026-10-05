import { pathToFileURL } from "node:url";
import { PrismaClient } from "@prisma/client";
import type { FastifyInstance } from "fastify";

import { config } from "@/config/env";
import { GetHelloUseCase } from "@/usecase/hello/get-hello.usecase";
import { GetHealthUseCase } from "@/usecase/health/get-health.usecase";
import { PrismaDatabaseHealthGateway } from "@/infra/gateway/prisma-database-health.gateway";
import { GetHelloHandler } from "@/infra/http/hello/get-hello.handler";
import { GetHealthHandler } from "@/infra/http/health/get-health.handler";
import { buildHttpRoutes } from "@/infra/http/index";
import { buildFastifyServer } from "@/infra/http/fastify-server";

export function bootstrap(): Promise<FastifyInstance> {
  const prisma = new PrismaClient({ datasources: { db: { url: config.databaseUrl } } });
  const databaseHealth = new PrismaDatabaseHealthGateway(prisma);
  const getHello = new GetHelloUseCase();
  const getHealth = new GetHealthUseCase(databaseHealth);
  const getHelloHandler = new GetHelloHandler(getHello);
  const getHealthHandler = new GetHealthHandler(getHealth);
  const routes = buildHttpRoutes({ getHelloHandler, getHealthHandler });
  const app = buildFastifyServer({ routes, logger: { level: config.logLevel } });

  app.addHook("onClose", () => prisma.$disconnect());
  return Promise.resolve(app);
}

async function start(): Promise<void> {
  const app = await bootstrap();
  await app.listen({ port: config.port, host: "0.0.0.0" });
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  await start();
}
