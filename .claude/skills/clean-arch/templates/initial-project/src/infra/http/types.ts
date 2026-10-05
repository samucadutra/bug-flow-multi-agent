/**
 * Framework-agnostic HTTP types. Handlers and routes speak in these types,
 * not in Express / Fastify / Hono types. The framework adapter in main.ts
 * translates between the chosen framework and these.
 */

export type HttpMethod = 'GET' | 'POST' | 'PUT' | 'PATCH' | 'DELETE';

export type HttpRequest = {
  method: HttpMethod;
  path: string;
  params: Record<string, string>;
  query: Record<string, string | string[] | undefined>;
  body: unknown;
  headers: Record<string, string | string[] | undefined>;
  user?: { id: string; isAdmin: boolean };
};

export type HttpResponse = {
  status: number;
  body?: unknown;
  headers?: Record<string, string>;
};

export type HttpRoute = {
  method: HttpMethod;
  path: string;
  handler: { handle(req: HttpRequest): Promise<HttpResponse> };
};
