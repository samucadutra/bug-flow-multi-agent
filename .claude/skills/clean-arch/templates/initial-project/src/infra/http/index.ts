import type { HttpRoute } from './types';

/**
 * Aggregator for per-feature route arrays.
 *
 * As features are added, import each `<feature>.routes.ts` here, extend
 * `HttpDeps` with that feature's deps type, and spread its routes into
 * the returned array.
 *
 * This is the single allowed `index.ts` barrel in the project (rule 4).
 */
export type HttpDeps = Record<string, never>;

export const buildHttpRoutes = (_deps: HttpDeps): HttpRoute[] => [
  // ...userRoutes(deps),
  // ...videoRoutes(deps),
];
