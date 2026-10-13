import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MainNav } from "@/components/shell/main-nav";

let pathname = "/";
vi.mock("next/navigation", () => ({ usePathname: () => pathname }));

beforeEach(() => {
  pathname = "/";
});

describe("MainNav", () => {
  it("lists the four links in order and marks the current page", () => {
    render(<MainNav />);
    const nav = screen.getByRole("navigation", { name: "Primary" });
    const links = within(nav).getAllByRole("link");
    expect(links.map((link) => link.textContent)).toEqual(["Dashboard", "Bugs", "Search", "Operations"]);
    expect(links.map((link) => link.getAttribute("href"))).toEqual(["/", "/bugs", "/search", "/operations"]);
    expect(screen.getByRole("link", { name: "Dashboard" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Bugs" })).not.toHaveAttribute("aria-current");
  });

  it("marks the matching section", () => {
    pathname = "/bugs";
    render(<MainNav />);
    expect(screen.getByRole("link", { name: "Bugs" })).toHaveAttribute("aria-current", "page");
    expect(screen.getByRole("link", { name: "Dashboard" })).not.toHaveAttribute("aria-current");
  });

  it("test_mobile_nav_toggle", async () => {
    render(<MainNav />);
    const button = screen.getByRole("button", { name: "Menu" });
    expect(button).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "true");
    await userEvent.click(button);
    expect(button).toHaveAttribute("aria-expanded", "false");
  });

  it("closes the menu when a link is chosen", async () => {
    render(<MainNav />);
    const button = screen.getByRole("button", { name: "Menu" });
    await userEvent.click(button);
    await userEvent.click(screen.getByRole("link", { name: "Bugs" }));
    expect(button).toHaveAttribute("aria-expanded", "false");
  });
});
