import { pathToFileURL } from "node:url";
import type { FastifyInstance } from "fastify";

import { config } from "@/config/env";
import { GetHelloUseCase } from "@/usecase/hello/get-hello.usecase";
import { GetHealthUseCase } from "@/usecase/health/get-health.usecase";
import { GetHelloHandler } from "@/infra/http/hello/get-hello.handler";
import { GetHealthHandler } from "@/infra/http/health/get-health.handler";
import { buildHttpRoutes } from "@/infra/http/index";
import { buildFastifyServer } from "@/infra/http/fastify-server";

export function bootstrap(): Promise<FastifyInstance> {
  const getHello = new GetHelloUseCase();
  const getHealth = new GetHealthUseCase();
  const getHelloHandler = new GetHelloHandler(getHello);
  const getHealthHandler = new GetHealthHandler(getHealth);
  const routes = buildHttpRoutes({ getHelloHandler, getHealthHandler });

  return Promise.resolve(buildFastifyServer({ routes, logger: { level: config.logLevel } }));
}

async function start(): Promise<void> {
  const app = await bootstrap();
  await app.listen({ port: config.port, host: "0.0.0.0" });
}

if (import.meta.url === pathToFileURL(process.argv[1] ?? "").href) {
  await start();
}
