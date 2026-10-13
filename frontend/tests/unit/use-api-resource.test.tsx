import { act, renderHook, waitFor } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { useApiResource } from "@/hooks/use-api-resource";
import { ApiError } from "@/lib/api";

describe("useApiResource", () => {
  it("goes from loading to success", async () => {
    const load = () => Promise.resolve("data");
    const { result } = renderHook(() => useApiResource(load));
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.data).toBe("data");
  });

  it("reports an ApiError and reloads", async () => {
    let calls = 0;
    const load = () => {
      calls += 1;
      return calls === 1 ? Promise.reject(new ApiError(503, "x", "Down")) : Promise.resolve(calls);
    };
    const { result } = renderHook(() => useApiResource(load));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error?.message).toBe("Down");
    act(() => result.current.reload());
    expect(result.current.status).toBe("loading");
    await waitFor(() => expect(result.current.status).toBe("success"));
    expect(result.current.data).toBe(2);
  });

  it("wraps unknown failures", async () => {
    const load = () => Promise.reject(new Error("secret stack"));
    const { result } = renderHook(() => useApiResource(load));
    await waitFor(() => expect(result.current.status).toBe("error"));
    expect(result.current.error?.message).not.toContain("secret");
  });
});
