import { describe, expect, it } from "vitest";
import { count, relative } from "./time";

describe("time", () => {
  it("relative times have units", () => {
    const now = Date.parse("2026-11-23T12:00:00Z");
    expect(relative("2026-11-23T11:55:00Z", now)).toBe("5 min ago");
    expect(relative("2026-11-23T09:00:00Z", now)).toBe("3 h ago");
    expect(relative("2026-11-20T12:00:00Z", now)).toBe("3 days ago");
  });
  it("counts say the noun", () => {
    expect(count(1, "test")).toBe("1 test");
    expect(count(7, "test")).toBe("7 tests");
  });
});
