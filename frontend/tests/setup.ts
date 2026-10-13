import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";
import { FakeEventSource } from "./fake-event-source";

vi.stubGlobal("EventSource", FakeEventSource);

afterEach(() => {
  cleanup();
  FakeEventSource.reset();
});
