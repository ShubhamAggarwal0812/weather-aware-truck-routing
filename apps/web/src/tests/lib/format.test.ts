import { describe, expect, it } from "vitest";
import { formatDuration, formatMiles, formatRanges, formatRate, nextQuarterHour } from "@/lib/format";

describe("format", () => {
  it("formats durations", () => {
    expect(formatDuration(45 * 60)).toBe("45 min");
    expect(formatDuration(3 * 3600)).toBe("3 h");
    expect(formatDuration(28 * 3600 + 19 * 60)).toBe("28 h 19 min");
  });

  it("formats miles and rates", () => {
    expect(formatMiles(1006.04)).toBe("1,006 mi");
    expect(formatMiles(12.34)).toBe("12.3 mi");
    expect(formatRate(0)).toBe("0");
    expect(formatRate(0.004)).toBe("<0.01");
    expect(formatRate(0.256)).toBe("0.26");
  });

  it("rounds up to the next quarter hour", () => {
    const d = nextQuarterHour(new Date(2026, 9, 12, 10, 7, 30));
    expect([d.getHours(), d.getMinutes()]).toEqual([10, 15]);
    expect(nextQuarterHour(new Date(2026, 9, 12, 10, 59)).getHours()).toBe(11);
  });

  it("should join a number range with an en dash that a line can't break around", () => {
    expect(formatRanges("45-54 mph wind")).toBe("45\u2060\u2013\u206054 mph wind");
  });

  it("should leave hyphens that aren't between numbers alone", () => {
    expect(formatRanges("fade-in after a 10-hour rest")).toBe("fade-in after a 10-hour rest");
  });
});
