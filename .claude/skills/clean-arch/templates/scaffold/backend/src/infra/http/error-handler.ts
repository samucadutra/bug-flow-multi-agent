import { AppError } from "@/domain/_shared/errors";
import type { HttpResponse } from "./types";

export function toHttpResponse(error: unknown): HttpResponse {
  if (error instanceof AppError) {
    return { status: error.status, body: { code: error.code, message: error.message } };
  }

  return {
    status: 500,
    body: { code: "internal_error", message: "Internal server error" },
  };
}
