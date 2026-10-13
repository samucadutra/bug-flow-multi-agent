import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { EmptyState } from "@/components/states/empty-state";
import { ErrorState } from "@/components/states/error-state";
import { LoadingState } from "@/components/states/loading-state";

describe("state components", () => {
  it("loading has role status and the text Loading", () => {
    render(<LoadingState />);
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
  });

  it("empty shows its message and optional action", () => {
    render(<EmptyState action={<a href="/x">Go</a>}>Nothing here.</EmptyState>);
    expect(screen.getByText("Nothing here.")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Go" })).toBeInTheDocument();
  });

  it("error has role alert and calls Retry", async () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Boom" onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Boom");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledOnce();
  });

  it("error without a callback has no Retry button", () => {
    render(<ErrorState message="Boom" />);
    expect(screen.queryByRole("button")).toBeNull();
  });
});
