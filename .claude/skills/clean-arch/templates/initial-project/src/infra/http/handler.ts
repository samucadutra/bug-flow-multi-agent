import type { HttpRequest, HttpResponse } from './types';

/**
 * Every handler implements this single-method interface.
 * `try/catch` is forbidden in handlers — exceptions propagate to the
 * framework adapter in main.ts, which calls toHttpResponse(err).
 */
export interface Handler {
  handle(req: HttpRequest): Promise<HttpResponse>;
}
