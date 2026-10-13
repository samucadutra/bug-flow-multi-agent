import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import finished from "../fixtures/run-7-finished.json";
import { FakeEventSource } from "../fake-event-source";
import { ApiError } from "@/lib/api";
import type { RunDetail } from "@/lib/api/types";
import { useRunProgress, type EventSourceFactory } from "@/hooks/use-run-progress";

const detail = finished as unknown as RunDetail;
const factory = FakeEventSource as unknown as EventSourceFactory;
const BASE = "http://127.0.0.1:8100/api/v1";

function runningDetail(stepCount: number, status: string): RunDetail {
  return {
    run: { ...detail.run, status, finished_at: status === "running" ? null : detail.run.finished_at },
    steps: detail.steps.slice(0, stepCount),
    logs: detail.logs.slice(0, stepCount),
  };
}

beforeEach(() => {
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("useRunProgress", () => {
  it("is idle without a run id and starts no activity", () => {
    const getRun = vi.fn();
    const { result } = renderHook(() => useRunProgress(null, { client: { getRun }, baseUrl: BASE }));
    expect(result.current.status).toBe("idle");
    expect(FakeEventSource.instances).toHaveLength(0);
    expect(getRun).not.toHaveBeenCalled();
  });

  it("test_progress_sse_closes_on_terminal_run", () => {
    const { result } = renderHook(() => useRunProgress(7, { eventSource: factory, baseUrl: BASE }));
    const source = FakeEventSource.instances[0];
    expect(source.url).toBe(`${BASE}/runs/7/events`);
    act(() => {
      source.emit("open");
      for (const step of detail.steps) source.emit("step", { type: "step", cursor: "c", step });
      // a repeated step event must not duplicate the entry
      source.emit("step", { type: "step", cursor: "c", step: detail.steps[0] });
      for (const log of detail.logs) source.emit("log", { type: "log", cursor: "c", log });
      source.emit("run", { type: "run", cursor: "c", run: detail.run });
    });
    expect(result.current.transport).toBe("sse");
    expect(result.current.steps.map((step) => step.position)).toEqual([1, 2, 3, 4, 5]);
    expect(result.current.logs).toHaveLength(4);
    expect(result.current.run?.status).toBe("succeeded");
    expect(result.current.status).toBe("done");
    expect(source.closed).toBe(true);
  });

  it("shows live events as streaming", () => {
    const { result } = renderHook(() => useRunProgress(8, { eventSource: factory, baseUrl: BASE }));
    act(() => {
      FakeEventSource.instances[0].emit("step", {
        type: "step",
        cursor: "1",
        step: { ...detail.steps[0], status: "running" },
      });
    });
    expect(result.current.status).toBe("streaming");
    expect(result.current.steps[0].status).toBe("running");
  });

  it("test_progress_falls_back_to_polling", async () => {
    const getRun = vi
      .fn()
      .mockResolvedValueOnce(runningDetail(1, "running"))
      .mockResolvedValueOnce(runningDetail(3, "running"))
      .mockResolvedValue(runningDetail(5, "succeeded"));
    const { result } = renderHook(() =>
      useRunProgress(8, { eventSource: factory, client: { getRun }, baseUrl: BASE }),
    );
    // one event arrives, then the stream fails
    act(() => {
      const source = FakeEventSource.instances[0];
      source.emit("step", { type: "step", cursor: "1", step: detail.steps[0] });
      source.emit("error");
    });
    expect(FakeEventSource.instances[0].closed).toBe(true);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.transport).toBe("polling");
    expect(getRun).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(999);
    });
    expect(getRun).toHaveBeenCalledTimes(1);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1);
    });
    expect(getRun).toHaveBeenCalledTimes(2);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1000);
    });
    expect(result.current.status).toBe("done");
    expect(result.current.steps.map((step) => step.position)).toEqual([1, 2, 3, 4, 5]);
    expect(result.current.logs).toHaveLength(4);
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(getRun).toHaveBeenCalledTimes(3);
  });

  it("polls directly when no event stream exists", async () => {
    const getRun = vi.fn().mockResolvedValue(runningDetail(5, "succeeded"));
    const { result } = renderHook(() =>
      useRunProgress(8, { eventSource: null, client: { getRun }, baseUrl: BASE }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    expect(result.current.status).toBe("done");
    expect(result.current.transport).toBe("polling");
  });

  it("ends in an error on an unknown run and stops polling", async () => {
    const getRun = vi.fn().mockRejectedValue(new ApiError(404, "not_found", "Run 999999 not found"));
    const { result } = renderHook(() =>
      useRunProgress(999999, { eventSource: null, client: { getRun }, baseUrl: BASE }),
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(result.current.status).toBe("error");
    expect(result.current.error?.code).toBe("not_found");
    expect(getRun).toHaveBeenCalledTimes(1);
  });

  it("test_progress_unmount_stops_activity", async () => {
    const getRun = vi.fn().mockResolvedValue(runningDetail(1, "running"));
    const { unmount } = renderHook(() =>
      useRunProgress(8, { eventSource: factory, client: { getRun }, baseUrl: BASE }),
    );
    const stream = FakeEventSource.instances[0];
    unmount();
    expect(stream.closed).toBe(true);

    const polling = renderHook(() => useRunProgress(8, { eventSource: null, client: { getRun }, baseUrl: BASE }));
    await act(async () => {
      await vi.advanceTimersByTimeAsync(0);
    });
    const callsBefore = getRun.mock.calls.length;
    polling.unmount();
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5000);
    });
    expect(getRun.mock.calls.length).toBe(callsBefore);
  });
});
