import { apiBaseUrl } from "@/lib/config";
import { ApiError, errorFromBody, httpError, networkError } from "./errors";
import type {
  Bug,
  BugCreate,
  BugDetail,
  BugListQuery,
  BugPage,
  BugUpdate,
  EnumsResponse,
  Health,
  InitResult,
  ReportFormat,
  ReportJson,
  RunDetail,
  RunIds,
  RunList,
  RunListQuery,
  SearchResponse,
  SimilarResponse,
  Stats,
  TriageTarget,
} from "./types";

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export interface ClientOptions {
  baseUrl?: string;
  /** Test-only injection; production code uses the browser fetch. */
  fetch?: FetchLike;
}

type Query = Record<string, string | number | boolean | undefined | null>;

function buildQuery(query: Query | undefined): string {
  if (!query) return "";
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value !== undefined && value !== null) params.append(key, String(value));
  }
  const text = params.toString();
  return text === "" ? "" : `?${text}`;
}

export function createApiClient(options: ClientOptions = {}) {
  const baseUrl = (options.baseUrl ?? apiBaseUrl).replace(/\/+$/, "");
  const doFetch: FetchLike = options.fetch ?? ((input, init) => fetch(input, init));

  async function send(method: string, path: string, query?: Query, body?: unknown): Promise<Response> {
    const init: RequestInit = { method };
    if (body !== undefined) {
      init.headers = { "Content-Type": "application/json" };
      init.body = JSON.stringify(body);
    }
    let response: Response;
    try {
      response = await doFetch(`${baseUrl}${path}${buildQuery(query)}`, init);
    } catch {
      throw networkError(baseUrl);
    }
    if (!response.ok) {
      let parsed: unknown = null;
      try {
        parsed = await response.json();
      } catch {
        parsed = null;
      }
      throw errorFromBody(response.status, parsed);
    }
    return response;
  }

  async function request<T>(method: string, path: string, query?: Query, body?: unknown): Promise<T> {
    const response = await send(method, path, query, body);
    try {
      return (await response.json()) as T;
    } catch {
      throw httpError(response.status);
    }
  }

  async function text(path: string, query?: Query): Promise<string> {
    return (await send("GET", path, query)).text();
  }

  return {
    health: () => request<Health>("GET", "/health"),
    enums: () => request<EnumsResponse>("GET", "/meta/enums"),
    stats: () => request<Stats>("GET", "/stats"),
    initDb: () => request<InitResult>("POST", "/admin/db/init"),
    resetDb: () => request<InitResult>("POST", "/admin/db/reset", undefined, { confirm: true }),
    seedDb: () => request<RunIds>("POST", "/admin/db/seed"),
    indexAll: () => request<RunIds>("POST", "/admin/index"),
    listBugs: (query: BugListQuery = {}) => request<BugPage>("GET", "/bugs", { ...query }),
    createBug: (body: BugCreate) => request<Bug>("POST", "/bugs", undefined, body),
    updateBug: (id: number, body: BugUpdate) => request<Bug>("PATCH", `/bugs/${id}`, undefined, body),
    getBug: (id: number) => request<BugDetail>("GET", `/bugs/${id}`),
    similarBugs: (id: number, limit?: number) =>
      request<SimilarResponse>("GET", `/bugs/${id}/similar`, { limit }),
    bugRuns: (id: number) => request<RunList>("GET", `/bugs/${id}/runs`),
    reopenBug: (id: number) => request<Bug>("POST", `/bugs/${id}/reopen`, undefined, { confirm: true }),
    getReport: ((id: number, format: ReportFormat = "json") =>
      format === "json"
        ? request<ReportJson>("GET", `/bugs/${id}/report`, { format })
        : text(`/bugs/${id}/report`, { format })) as {
      (id: number, format?: "json"): Promise<ReportJson>;
      (id: number, format: "md" | "html"): Promise<string>;
    },
    search: (q: string, limit?: number) => request<SearchResponse>("GET", "/search", { q, limit }),
    startTriage: (target: TriageTarget) => request<RunIds>("POST", "/triage-runs", undefined, target),
    listRuns: (query: RunListQuery = {}) => request<RunList>("GET", "/runs", { ...query }),
    getRun: (id: number) => request<RunDetail>("GET", `/runs/${id}`),
  };
}

export type ApiClient = ReturnType<typeof createApiClient>;

/** Shared instance bound to the configured base URL. */
export const api: ApiClient = createApiClient();

export { ApiError };
