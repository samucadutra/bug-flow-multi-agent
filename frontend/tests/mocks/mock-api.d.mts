import type { Server } from "node:http";

export interface MockApi {
  server: Server;
  readonly scenario: string;
  start(): Promise<number>;
  stop(): Promise<void>;
}

export function createMockApi(options?: { port?: number; scenario?: string }): MockApi;
