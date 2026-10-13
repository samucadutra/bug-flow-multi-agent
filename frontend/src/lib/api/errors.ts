import type { ErrorEnvelope } from "./types";

export type ApiErrorCode = "network_error" | "http_error" | (string & {});

/** Every client failure rejects with this error; messages never include a stack trace. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: ApiErrorCode;
  readonly details: unknown[];

  constructor(status: number, code: ApiErrorCode, message: string, details: unknown[] = []) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

export function networkError(baseUrl: string): ApiError {
  return new ApiError(
    0,
    "network_error",
    `Cannot reach the BugFlow API at ${baseUrl}. Check that the server is running.`,
  );
}

export function httpError(status: number): ApiError {
  return new ApiError(status, "http_error", `The API returned an unexpected response (HTTP ${status}).`);
}

function isEnvelope(value: unknown): value is ErrorEnvelope {
  if (typeof value !== "object" || value === null || !("error" in value)) return false;
  const error = (value as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
}

/** Map a non-2xx response body to a typed error. */
export function errorFromBody(status: number, body: unknown): ApiError {
  if (isEnvelope(body)) {
    const { code, message, details } = body.error;
    return new ApiError(status, code, message, Array.isArray(details) ? details : []);
  }
  return httpError(status);
}
