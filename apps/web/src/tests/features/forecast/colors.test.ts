import { describe, expect, it } from "vitest";
import { rampsFor } from "@/features/forecast/heatmap/colors";
import { RISK_COLOR, RISK_ORDER } from "@/lib/risk";
import { RULES } from "../../fixtures/plan";

const channels = (hex: string) => [1, 3, 5].map((offset) => parseInt(hex.slice(offset, offset + 2), 16));
const colourAt = (lookupTable: Uint8ClampedArray, entry: number) =>
  Array.from(lookupTable.slice(entry * 4, entry * 4 + 3));

describe("rampsFor", () => {
  it("should put each colour change on the rules' thresholds", () => {
    const wind = rampsFor(RULES).wind_mph;
    const colourOfStopAt = (value: number) => wind.stops.find((stop) => stop.value === value)?.color;
    expect(colourOfStopAt(25)).toBe(RISK_COLOR.moderate);
    expect(colourOfStopAt(35)).toBe(RISK_COLOR.high);
    expect(colourOfStopAt(45)).toBe(RISK_COLOR.severe);
    expect(colourOfStopAt(55)).toBe(RISK_COLOR.no_travel);
  });

  it("should follow the rules when a threshold changes", () => {
    const rules = { ...RULES, wind_mph: [{ level: "moderate" as const, threshold: 10, inclusive: true }] };
    const values = rampsFor(rules).wind_mph.stops.map((stop) => stop.value);
    // The 12 miles per hour fade-in stop would sit above Moderate, so it is dropped.
    expect(values).toEqual([0, 10, 20]);
    expect(rampsFor(rules).wind_mph.stops[1].color).toBe(RISK_COLOR.moderate);
  });

  it("should draw risk in the level colours only", () => {
    const risk = rampsFor(RULES).risk;
    const allowed = RISK_ORDER.map((key) => channels(RISK_COLOR[key]).join());
    for (let entry = 0; entry < 256; entry++) expect(allowed).toContain(colourAt(risk.lut, entry).join());
    RISK_ORDER.forEach((key, score) => {
      expect(colourAt(risk.lut, Math.round((score / 4) * 255))).toEqual(channels(RISK_COLOR[key]));
    });
  });

  it("should reuse the ramps built for the same rules", () => {
    expect(rampsFor(RULES)).toBe(rampsFor(RULES));
  });
});
