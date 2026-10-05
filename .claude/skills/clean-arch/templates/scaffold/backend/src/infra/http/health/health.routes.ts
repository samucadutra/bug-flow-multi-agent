import type { GetHealthHandler } from "./get-health.handler";
import type { HttpRoute } from "@/infra/http/types";

export type HealthHttpDeps = {
  getHealthHandler: GetHealthHandler;
};

export const healthRoutes = (deps: HealthHttpDeps): HttpRoute[] => [
  { method: "GET", path: "/health", handler: deps.getHealthHandler },
];
