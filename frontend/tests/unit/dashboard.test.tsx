import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import enums from "../fixtures/enums.json";
import runs from "../fixtures/runs-recent.json";
import statsEmpty from "../fixtures/stats-empty.json";
import statsPopulated from "../fixtures/stats-populated.json";
import { Dashboard } from "@/components/dashboard/dashboard";
import { api } from "@/lib/api";
import { ApiError } from "@/lib/api/errors";
import { EnumProvider } from "@/providers/enum-provider";

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));

function renderDashboard() {
  return render(
    <EnumProvider>
      <Dashboard />
    </EnumProvider>,
  );
}

function stub(overrides: Partial<Record<"enums" | "stats" | "listRuns", () => Promise<unknown>>> = {}) {
  vi.spyOn(api, "enums").mockImplementation((overrides.enums ?? (() => Promise.resolve(enums))) as never);
  vi.spyOn(api, "stats").mockImplementation((overrides.stats ?? (() => Promise.resolve(statsPopulated))) as never);
  vi.spyOn(api, "listRuns").mockImplementation(
    (overrides.listRuns ?? ((query?: { limit?: number }) => Promise.resolve({ items: runs.items.slice(0, query?.limit) }))) as never,
  );
}

const down = () => Promise.reject(new ApiError(0, "network_error", "Cannot reach the BugFlow API at http://x/api/v1. Check that the server is running."));

beforeEach(() => {
  vi.restoreAllMocks();
});

afterEach(() => {
  vi.restoreAllMocks();
});

describe("Dashboard", () => {
  it("shows loading first", () => {
    stub();
    renderDashboard();
    expect(screen.getByRole("status")).toHaveTextContent("Loading");
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("test_dashboard_counts_follow_enum_order", async () => {
    stub();
    renderDashboard();
    const group = await screen.findByRole("region", { name: "By status" });
    const entries = within(group).getAllByRole("listitem").map((item) => item.textContent);
    expect(entries).toEqual(["Open17", "Processing1", "Processed2", "Failed0"]);
    const components = within(screen.getByRole("region", { name: "By component" })).getAllByRole("listitem");
    expect(components).toHaveLength(8);
    expect(components[0]).toHaveTextContent("Frontend1");
    expect(components[6]).toHaveTextContent("UI/UX0");
    const severities = within(screen.getByRole("region", { name: "By severity" })).getAllByRole("listitem");
    expect(severities.map((item) => item.textContent)).toEqual(["Critical0", "Major1", "Minor1"]);
    expect(screen.getByText("Total bugs:").textContent).toContain("20");
  });

  it("lists the 10 most recent runs with duration and link", async () => {
    stub();
    renderDashboard();
    const section = await screen.findByRole("region", { name: "Recent runs" });
    const rows = within(section).getAllByRole("listitem");
    expect(rows).toHaveLength(10);
    expect(api.listRuns).toHaveBeenCalledWith({ limit: 10 });
    expect(rows[0]).toHaveTextContent("Triage");
    expect(rows[0]).toHaveTextContent("Running");
    expect(rows[0]).toHaveTextContent("—");
    expect(rows[1]).toHaveTextContent("1 m 2 s");
    expect(rows[2]).toHaveTextContent("41 s");
    expect(within(rows[2]).getByRole("link")).toHaveAttribute("href", "/runs/19");
  });

  it("test_dashboard_empty_state_text", async () => {
    stub({ stats: () => Promise.resolve(statsEmpty), listRuns: () => Promise.resolve({ items: [] }) });
    renderDashboard();
    const message = await screen.findByText(/No bugs yet\./);
    expect(message.textContent).toBe("No bugs yet. Go to Operations to initialize and seed the database.");
    expect(within(message).getByRole("link", { name: "Operations" })).toHaveAttribute("href", "/operations");
    expect(screen.queryByRole("region", { name: "By status" })).toBeNull();
    expect(screen.getByText("No runs yet.")).toBeInTheDocument();
    expect(screen.queryAllByRole("listitem")).toHaveLength(0);
  });

  it("test_dashboard_error_retry", async () => {
    let attempt = 0;
    stub({
      stats: () => {
        attempt += 1;
        return attempt === 1 ? down() : Promise.resolve(statsPopulated);
      },
    });
    renderDashboard();
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Cannot reach the BugFlow API");
    expect(screen.queryByRole("region", { name: "By status" })).toBeNull();
    await userEvent.click(within(banner).getByRole("button", { name: "Retry" }));
    await waitFor(() => expect(screen.getByRole("region", { name: "By status" })).toBeInTheDocument());
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("shows an error, not raw codes, when the enums fail, and recovers", async () => {
    let attempt = 0;
    stub({
      enums: () => {
        attempt += 1;
        return attempt === 1
          ? Promise.reject(new ApiError(503, "service_unavailable", "Database is unavailable"))
          : Promise.resolve(enums);
      },
    });
    renderDashboard();
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent("Database is unavailable");
    expect(screen.queryByText("open")).toBeNull();
    await userEvent.click(within(banner).getByRole("button", { name: "Retry" }));
    await screen.findByRole("region", { name: "By status" });
  });

  it("shows the envelope message of a failing runs request", async () => {
    stub({ listRuns: () => Promise.reject(new ApiError(500, "internal_error", "Internal server error")) });
    renderDashboard();
    expect(await screen.findByRole("alert")).toHaveTextContent("Internal server error");
  });

  it("falls back to the code for a count the enums do not list", async () => {
    stub({ stats: () => Promise.resolve({ ...statsPopulated, by_status: { ...statsPopulated.by_status, mystery: 3 } }) });
    renderDashboard();
    const group = await screen.findByRole("region", { name: "By status" });
    expect(within(group).getByText("mystery")).toBeInTheDocument();
  });
});
