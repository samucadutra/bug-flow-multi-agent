export interface DatabaseHealthGateway {
  check(): Promise<"ok" | "unreachable">;
}
