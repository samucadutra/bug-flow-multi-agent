export type GetHealthInput = Record<string, never>;

export type GetHealthOutput = {
  status: "ok" | "degraded";
  db: "ok" | "unreachable";
};
