import type { GetHelloHandler } from "./get-hello.handler";
import type { HttpRoute } from "@/infra/http/types";

export type HelloHttpDeps = {
  getHelloHandler: GetHelloHandler;
};

export const helloRoutes = (deps: HelloHttpDeps): HttpRoute[] => [
  { method: "GET", path: "/api/hello", handler: deps.getHelloHandler },
];
