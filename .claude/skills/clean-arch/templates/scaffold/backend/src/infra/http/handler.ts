import type { HttpRequest, HttpResponse } from "./types";

export interface Handler {
  handle(req: HttpRequest): Promise<HttpResponse>;
}
