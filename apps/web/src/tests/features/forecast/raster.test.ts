import { describe, expect, it } from "vitest";
import { buildRamp } from "@/features/forecast/heatmap/colors";
import { buildLayout, buildSampler, paint, valuesAt } from "@/features/forecast/heatmap/raster";

// A 2 x 3 grid of cells with step 1 degree around (40..41N, -100..-98E); one cell missing.
const corridor = {
  step_deg: 1,
  rows: [40, 40, 40, 41, 41],
  cols: [-100, -99, -98, -100, -99],
};

describe("buildLayout", () => {
  it("maps cells into a dense grid with half-cell margins", () => {
    const layout = buildLayout(corridor);
    expect([layout.nrows, layout.ncols]).toEqual([2, 3]);
    expect(layout.bounds).toEqual({ west: -100.5, east: -97.5, south: 39.5, north: 41.5 });
    expect(Array.from(layout.cellAt)).toEqual([0, 1, 2, 3, 4, -1]);
  });
});

describe("buildSampler", () => {
  const layout = buildLayout(corridor);
  const sampler = buildSampler(layout, 10_000);

  it("keeps a Mercator aspect ratio", () => {
    // At 40N a degree of longitude is ~0.77 of a degree of latitude, so the
    // 3 x 2 degree box is taller than 2:3 in Mercator.
    const ratio = sampler.height / sampler.width;
    expect(ratio).toBeGreaterThan(0.85);
    expect(ratio).toBeLessThan(0.9);
  });

  it("weights sum to one where all four cells exist", () => {
    const { width, height, weights, cells } = sampler;
    const p = Math.floor(height * 0.5) * width + Math.floor(width * 0.4);
    const w = weights.slice(p * 4, p * 4 + 4).reduce((a, b) => a + b, 0);
    expect(w).toBeCloseTo(1, 5);
    expect(Array.from(cells.slice(p * 4, p * 4 + 4)).every((c) => c >= 0)).toBe(true);
  });
});

describe("paint", () => {
  const layout = buildLayout(corridor);
  const sampler = buildSampler(layout, 10_000);
  const ramp = buildRamp([
    { value: 0, color: "#000000", alpha: 1 },
    { value: 10, color: "#ffffff", alpha: 1 },
  ]);

  it("interpolates between cells and leaves the missing corner transparent", () => {
    const image = new Uint8ClampedArray(sampler.width * sampler.height * 4);
    paint(sampler, Float32Array.from([0, 10, 10, 0, 10]), ramp, image);
    const pixel = (fx: number, fy: number) => {
      const p = (Math.floor(fy * (sampler.height - 1)) * sampler.width + Math.floor(fx * (sampler.width - 1))) * 4;
      return Array.from(image.slice(p, p + 4));
    };
    // Bottom-left cell centre (value 0) is black, the cell to its right (10) white.
    expect(pixel(1 / 6, 0.78)[0]).toBeLessThan(40);
    expect(pixel(3 / 6, 0.78)[0]).toBeGreaterThan(215);
    // Top-right corner has no cell: fully transparent.
    expect(pixel(0.99, 0.01)[3]).toBe(0);
  });
});

describe("valuesAt", () => {
  it("blends neighbouring hours and clamps to the window", () => {
    const hours = [Float32Array.from([0, 10]), Float32Array.from([10, 30])];
    const out = new Float32Array(2);
    expect(Array.from(valuesAt(hours, 0.25, out))).toEqual([2.5, 15]);
    expect(Array.from(valuesAt(hours, 5, out))).toEqual([10, 30]);
    expect(Array.from(valuesAt(hours, -1, out))).toEqual([0, 10]);
  });
});

describe("buildRamp", () => {
  it("hits stop colours exactly", () => {
    const r = buildRamp([
      { value: 0, color: "#ff0000", alpha: 0 },
      { value: 1, color: "#0000ff", alpha: 1 },
    ]);
    expect(Array.from(r.lut.slice(0, 4))).toEqual([255, 0, 0, 0]);
    expect(Array.from(r.lut.slice(255 * 4, 256 * 4))).toEqual([0, 0, 255, 255]);
  });
});
