import { render, renderHook, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";
import enumsFixture from "../fixtures/enums.json";
import { ApiError, type ApiClient } from "@/lib/api";
import { EnumProvider, useEnums } from "@/providers/enum-provider";

function clientWith(enums: () => Promise<unknown>) {
  return { enums: vi.fn(enums) } as unknown as ApiClient & { enums: ReturnType<typeof vi.fn> };
}

function wrapperFor(client: ApiClient) {
  return function Wrapper({ children }: { children: ReactNode }) {
    return <EnumProvider client={client}>{children}</EnumProvider>;
  };
}

describe("EnumProvider", () => {
  it("test_enum_provider_single_request", async () => {
    const client = clientWith(() => Promise.resolve(enumsFixture));
    function Consumer({ id }: { id: string }) {
      const enums = useEnums();
      return <span data-testid={id}>{enums.status}</span>;
    }
    render(
      <EnumProvider client={client}>
        <Consumer id="a" />
        <Consumer id="b" />
      </EnumProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("a")).toHaveTextContent("ready"));
    expect(screen.getByTestId("b")).toHaveTextContent("ready");
    expect(client.enums).toHaveBeenCalledTimes(1);
  });

  it("returns labels and values in the order served", async () => {
    const client = clientWith(() => Promise.resolve(enumsFixture));
    const { result } = renderHook(() => useEnums(), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.label("BugStatus", "processed")).toBe("Processed");
    expect(result.current.values("Severity").map((item) => item.code)).toEqual(["critical", "major", "minor"]);
    expect(result.current.values("Severity")[0]).toHaveProperty("definition");
  });

  it("test_enum_unknown_code_returns_code", async () => {
    const client = clientWith(() => Promise.resolve(enumsFixture));
    const { result } = renderHook(() => useEnums(), { wrapper: wrapperFor(client) });
    await waitFor(() => expect(result.current.status).toBe("ready"));
    expect(result.current.label("Component", "quantum")).toBe("quantum");
    expect(result.current.label("Nope", "x")).toBe("x");
    expect(client.enums).toHaveBeenCalledTimes(1);
  });

  it("reports a load failure without a fallback and recovers on retry", async () => {
    let attempt = 0;
    const client = clientWith(() => {
      attempt += 1;
      return attempt === 1
        ? Promise.reject(new ApiError(503, "service_unavailable", "Database is unavailable"))
        : Promise.resolve(enumsFixture);
    });
    function Probe() {
      const enums = useEnums();
      return (
        <div>
          <span data-testid="status">{enums.status}</span>
          <span data-testid="error">{enums.error?.message}</span>
          <span data-testid="label">{enums.label("BugStatus", "processed")}</span>
          <button onClick={enums.retry}>again</button>
        </div>
      );
    }
    render(
      <EnumProvider client={client}>
        <Probe />
      </EnumProvider>,
    );
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("error"));
    expect(screen.getByTestId("error")).toHaveTextContent("Database is unavailable");
    expect(screen.getByTestId("label")).toHaveTextContent("processed");
    await userEvent.click(screen.getByRole("button", { name: "again" }));
    await waitFor(() => expect(screen.getByTestId("status")).toHaveTextContent("ready"));
    expect(screen.getByTestId("label")).toHaveTextContent("Processed");
  });

  it("throws outside the provider", () => {
    expect(() => renderHook(() => useEnums())).toThrow();
  });
});
