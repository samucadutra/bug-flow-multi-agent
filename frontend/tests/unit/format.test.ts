import { describe, expect, it } from "vitest";
import { formatDuration } from "@/lib/format";

describe("formatDuration", () => {
  it("test_duration_format", () => {
    expect(formatDuration("2026-10-12T09:00:00Z", "2026-10-12T09:00:41Z")).toBe("41 s");
    expect(formatDuration("2026-10-12T10:00:00Z", "2026-10-12T10:01:02Z")).toBe("1 m 2 s");
    expect(formatDuration("2026-10-12T10:00:00Z", null)).toBe("—");
  });

  it("handles zero and unparsable values", () => {
    expect(formatDuration("2026-10-12T10:00:00Z", "2026-10-12T10:00:00Z")).toBe("0 s");
    expect(formatDuration("nope", "2026-10-12T10:00:00Z")).toBe("—");
  });
});
