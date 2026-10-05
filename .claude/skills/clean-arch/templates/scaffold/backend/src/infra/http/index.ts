import { helloRoutes, type HelloHttpDeps } from "./hello/hello.routes";
import { healthRoutes, type HealthHttpDeps } from "./health/health.routes";
import type { HttpRoute } from "./types";

export type HttpDeps = HelloHttpDeps & HealthHttpDeps;

export const buildHttpRoutes = (deps: HttpDeps): HttpRoute[] => [
  ...healthRoutes(deps),
  ...helloRoutes(deps),
];
