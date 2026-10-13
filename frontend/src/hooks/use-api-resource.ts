"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError } from "@/lib/api/errors";

export type ResourceState<T> =
  | { status: "loading"; data: null; error: null }
  | { status: "success"; data: T; error: null }
  | { status: "error"; data: null; error: ApiError };

const LOADING = { status: "loading", data: null, error: null } as const;

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(0, "unexpected_error", "Something went wrong while loading the data.");
}

/**
 * Run `load` on mount and whenever `reload` is called. `load` must be a stable function
 * (module level or memoized): a new identity starts a new request.
 */
export function useApiResource<T>(load: () => Promise<T>): ResourceState<T> & { reload: () => void } {
  const [state, setState] = useState<ResourceState<T>>(LOADING);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    load().then(
      (data) => {
        if (!cancelled) setState({ status: "success", data, error: null });
      },
      (error: unknown) => {
        if (!cancelled) setState({ status: "error", data: null, error: toApiError(error) });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [load, attempt]);

  const reload = useCallback(() => {
    setState(LOADING);
    setAttempt((value) => value + 1);
  }, []);

  return { ...state, reload };
}
