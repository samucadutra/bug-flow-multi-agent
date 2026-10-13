"use client";

import { useEffect, useMemo, useReducer } from "react";
import { api, type ApiClient } from "@/lib/api";
import { ApiError } from "@/lib/api/errors";
import type { Run, RunDetail, RunEvent, RunLog, RunStep } from "@/lib/api/types";
import { apiBaseUrl } from "@/lib/config";

export type ProgressStatus = "idle" | "connecting" | "streaming" | "polling" | "done" | "error";
export type ProgressTransport = "sse" | "polling" | null;

export interface RunProgress {
  status: ProgressStatus;
  transport: ProgressTransport;
  run: Run | null;
  steps: RunStep[];
  logs: RunLog[];
  error: ApiError | null;
}

/** The subset of `EventSource` that the hook uses; tests inject a fake. */
export interface EventSourceLike {
  addEventListener(type: string, listener: (event: MessageEvent<string>) => void): void;
  close(): void;
}
export type EventSourceFactory = new (url: string) => EventSourceLike;

export interface RunProgressOptions {
  /** Test-only injection; defaults to the browser `EventSource`. */
  eventSource?: EventSourceFactory | null;
  client?: Pick<ApiClient, "getRun">;
  pollIntervalMs?: number;
  baseUrl?: string;
}

const POLL_INTERVAL_MS = 1000;
const OPEN_EVENT = "open"; // check-enums: allow (EventSource event name, not display text)

interface State {
  runId: number | null;
  status: ProgressStatus;
  transport: ProgressTransport;
  run: Run | null;
  steps: Record<number, RunStep>;
  logs: Record<number, RunLog>;
  error: ApiError | null;
}

type Action =
  | { runId: number; kind: "streaming" }
  | { runId: number; kind: "polling" }
  | { runId: number; kind: "event"; event: RunEvent }
  | { runId: number; kind: "snapshot"; detail: RunDetail }
  | { runId: number; kind: "fail"; error: ApiError };

function initial(runId: number | null): State {
  return {
    runId,
    status: runId === null ? "idle" : "connecting",
    transport: null,
    run: null,
    steps: {},
    logs: {},
    error: null,
  };
}

const TERMINAL_RUN_STATES = ["succeeded", "failed"]; // check-enums: allow (protocol state, not display text)

function isTerminal(run: Run | null): boolean {
  return run !== null && TERMINAL_RUN_STATES.includes(run.status);
}

function withRun(state: State, run: Run): State {
  const next = { ...state, run };
  return isTerminal(run) ? { ...next, status: "done" } : next;
}

function reducer(previous: State, action: Action): State {
  const state = previous.runId === action.runId ? previous : initial(action.runId);
  if (state.status === "done" || state.status === "error") {
    // A finished or failed follow ignores late deliveries.
    return state;
  }
  switch (action.kind) {
    case "streaming":
      return { ...state, status: "streaming", transport: "sse" };
    case "polling":
      return { ...state, status: "polling", transport: "polling" };
    case "event": {
      const { event } = action;
      const live: State =
        state.transport === "polling" ? state : { ...state, status: "streaming", transport: "sse" };
      if (event.type === "step") {
        return { ...live, steps: { ...live.steps, [event.step.position]: event.step } };
      }
      if (event.type === "log") {
        return { ...live, logs: { ...live.logs, [event.log.id]: event.log } };
      }
      return withRun(live, event.run);
    }
    case "snapshot": {
      const steps = { ...state.steps };
      for (const step of action.detail.steps) steps[step.position] = step;
      const logs = { ...state.logs };
      for (const log of action.detail.logs) logs[log.id] = log;
      return withRun({ ...state, steps, logs }, action.detail.run);
    }
    case "fail":
      return { ...state, status: "error", error: action.error };
  }
}

function toApiError(error: unknown): ApiError {
  if (error instanceof ApiError) return error;
  return new ApiError(0, "unexpected_error", "Something went wrong while following the run.");
}

export function useRunProgress(runId: number | null, options: RunProgressOptions = {}): RunProgress {
  const [state, dispatch] = useReducer(reducer, runId, initial);
  const getRun = (options.client ?? api).getRun;
  const pollIntervalMs = options.pollIntervalMs ?? POLL_INTERVAL_MS;
  const baseUrl = options.baseUrl ?? apiBaseUrl;
  const injected = options.eventSource;

  useEffect(() => {
    if (runId === null) return;
    let cancelled = false;
    let finished = false;
    let source: EventSourceLike | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const stopSource = () => {
      source?.close();
      source = null;
    };

    const poll = async () => {
      try {
        const detail = await getRun(runId);
        if (cancelled) return;
        dispatch({ runId, kind: "snapshot", detail });
        if (isTerminal(detail.run)) {
          finished = true;
          return;
        }
      } catch (error) {
        if (!cancelled) dispatch({ runId, kind: "fail", error: toApiError(error) });
        return;
      }
      if (!cancelled) timer = setTimeout(poll, pollIntervalMs);
    };

    const startPolling = () => {
      stopSource();
      if (cancelled || finished) return;
      dispatch({ runId, kind: "polling" });
      void poll();
    };

    const Factory: EventSourceFactory | null =
      injected !== undefined
        ? injected
        : typeof EventSource === "undefined"
          ? null
          : (EventSource as unknown as EventSourceFactory);

    if (Factory === null) {
      startPolling();
    } else {
      source = new Factory(`${baseUrl}/runs/${runId}/events`);
      source.addEventListener(OPEN_EVENT, () => {
        if (!cancelled) dispatch({ runId, kind: "streaming" });
      });
      for (const type of ["step", "log", "run"] as const) {
        source.addEventListener(type, (message) => {
          if (cancelled) return;
          let event: RunEvent;
          try {
            event = JSON.parse(message.data) as RunEvent;
          } catch {
            return;
          }
          dispatch({ runId, kind: "event", event });
          if (event.type === "run" && isTerminal(event.run)) {
            finished = true;
            stopSource();
          }
        });
      }
      source.addEventListener("error", () => {
        if (!cancelled) startPolling();
      });
    }

    return () => {
      cancelled = true;
      stopSource();
      if (timer !== null) clearTimeout(timer);
    };
  }, [runId, getRun, pollIntervalMs, baseUrl, injected]);

  const current = state.runId === runId ? state : initial(runId);
  const steps = useMemo(
    () => Object.values(current.steps).sort((a, b) => a.position - b.position),
    [current.steps],
  );
  const logs = useMemo(() => Object.values(current.logs).sort((a, b) => a.id - b.id), [current.logs]);

  return { status: current.status, transport: current.transport, run: current.run, steps, logs, error: current.error };
}
