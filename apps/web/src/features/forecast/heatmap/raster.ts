/**
 * Turns the corridor forecast grid into a smooth image that MapLibre drapes over the map.
 *
 * - Values are interpolated bilinearly between grid cells, and linearly between
 *   forecast hours, so the 0–48 h slider moves continuously instead of jumping.
 *   Risk levels are not, because blending two levels would show levels that aren't there.
 * - Image rows are spaced in Web Mercator, not latitude, so the picture lines
 *   up with the basemap at any zoom.
 * - Cells outside the corridor are missing; pixels near them fade out instead of
 *   ending in a hard staircase edge.
 *
 * The per-pixel sampling (which 4 cells, which weights) depends only on the grid,
 * so it is computed once. A frame is then one multiply-add pass over the pixels.
 */
import type { Corridor, HeatVariable } from "@/lib/api/types";
import type { Ramp } from "./colors";

export interface GridLayout {
  step: number;
  rmin: number;
  cmin: number;
  nrows: number;
  ncols: number;
  /** Dense (row - rmin) * ncols + (col - cmin) -> cell index, or -1 outside the corridor. */
  cellAt: Int32Array;
  bounds: { west: number; east: number; south: number; north: number };
}

export function buildLayout(corridor: Pick<Corridor, "step_deg" | "rows" | "cols">): GridLayout {
  const { step_deg: step, rows, cols } = corridor;
  const rmin = Math.min(...rows);
  const cmin = Math.min(...cols);
  const nrows = Math.max(...rows) - rmin + 1;
  const ncols = Math.max(...cols) - cmin + 1;
  const cellAt = new Int32Array(nrows * ncols).fill(-1);
  rows.forEach((r, k) => {
    cellAt[(r - rmin) * ncols + (cols[k] - cmin)] = k;
  });
  return {
    step,
    rmin,
    cmin,
    nrows,
    ncols,
    cellAt,
    bounds: {
      west: (cmin - 0.5) * step,
      east: (cmin + ncols - 0.5) * step,
      south: (rmin - 0.5) * step,
      north: (rmin + nrows - 0.5) * step,
    },
  };
}

const mercY = (latDeg: number) => Math.log(Math.tan(Math.PI / 4 + (latDeg * Math.PI) / 360));
const latFromMercY = (y: number) => (Math.atan(Math.exp(y)) * 360) / Math.PI - 90;

/** Maps lon/lat to pixel coordinates of the heatmap image (Web Mercator rows). */
export function projector(layout: GridLayout, width: number, height: number) {
  const { west, east, south, north } = layout.bounds;
  const yTop = mercY(north);
  const yRange = yTop - mercY(south);
  return (lon: number, lat: number): [number, number] => [
    ((lon - west) / (east - west)) * width,
    ((yTop - mercY(lat)) / yRange) * height,
  ];
}

export interface Sampler {
  width: number;
  height: number;
  /** 4 cell indices per pixel (-1 = none). */
  cells: Int32Array;
  /** 4 bilinear weights per pixel. */
  weights: Float32Array;
  nearestCells: Int32Array;
}

export function buildSampler(layout: GridLayout, maxPixels = 260_000): Sampler {
  const { west, east, south, north } = layout.bounds;
  const mercWidth = ((east - west) * Math.PI) / 180;
  const mercHeight = mercY(north) - mercY(south);
  // About 8 px per cell is plenty: bilinear filtering on the GPU smooths the rest.
  let width = layout.ncols * 8;
  let height = Math.max(1, Math.round((width * mercHeight) / mercWidth));
  const scale = Math.min(1, Math.sqrt(maxPixels / (width * height)));
  width = Math.max(2, Math.round(width * scale));
  height = Math.max(2, Math.round(height * scale));

  const cells = new Int32Array(width * height * 4).fill(-1);
  const weights = new Float32Array(width * height * 4);
  const nearestCells = new Int32Array(width * height).fill(-1);
  const { step, rmin, cmin, nrows, ncols, cellAt } = layout;
  const yTop = mercY(north);
  const at = (r: number, c: number) => (r < 0 || c < 0 || r >= nrows || c >= ncols ? -1 : cellAt[r * ncols + c]);

  for (let py = 0; py < height; py++) {
    const lat = latFromMercY(yTop - ((py + 0.5) / height) * mercHeight);
    const gy = lat / step - rmin;
    const r0 = Math.floor(gy);
    const fy = gy - r0;
    for (let px = 0; px < width; px++) {
      const lon = west + ((px + 0.5) / width) * (east - west);
      const gx = lon / step - cmin;
      const c0 = Math.floor(gx);
      const fx = gx - c0;
      const o = (py * width + px) * 4;
      cells[o] = at(r0, c0);
      cells[o + 1] = at(r0, c0 + 1);
      cells[o + 2] = at(r0 + 1, c0);
      cells[o + 3] = at(r0 + 1, c0 + 1);
      weights[o] = (1 - fx) * (1 - fy);
      weights[o + 1] = fx * (1 - fy);
      weights[o + 2] = (1 - fx) * fy;
      weights[o + 3] = fx * fy;
      let nearestCorner = -1;
      for (let corner = 0; corner < 4; corner++) {
        const closer = nearestCorner < 0 || weights[o + corner] > weights[o + nearestCorner];
        if (cells[o + corner] >= 0 && closer) nearestCorner = corner;
      }
      nearestCells[py * width + px] = nearestCorner < 0 ? -1 : cells[o + nearestCorner];
    }
  }
  return { width, height, cells, weights, nearestCells };
}

/** Cell values at fractional hour ``t``, blending the two neighbouring forecast hours. */
export function valuesAt(hours: Float32Array[], t: number, out: Float32Array): Float32Array {
  const last = hours.length - 1;
  const clamped = Math.min(Math.max(t, 0), last);
  const h0 = Math.floor(clamped);
  const h1 = Math.min(h0 + 1, last);
  const f = clamped - h0;
  const a = hours[h0];
  const b = hours[h1];
  for (let i = 0; i < out.length; i++) out[i] = a[i] + (b[i] - a[i]) * f;
  return out;
}

/**
 * Writes one RGBA frame. ``image`` must be width * height * 4 long. ``mask`` (0..1 per
 * pixel) shapes the corridor; without it the edge follows the grid cells.
 */
export function paint(
  sampler: Sampler,
  values: Float32Array,
  ramp: Ramp,
  image: Uint8ClampedArray,
  mask?: Float32Array,
  categorical = false,
): void {
  const { cells, weights, nearestCells } = sampler;
  const { lut, min, max } = ramp;
  const scale = 255 / (max - min);
  const n = sampler.width * sampler.height;
  for (let p = 0; p < n; p++) {
    const o = p * 4;
    let sum = 0;
    let wsum = 0;
    for (let k = 0; k < 4; k++) {
      const cell = cells[o + k];
      if (cell >= 0) {
        const w = weights[o + k];
        sum += values[cell] * w;
        wsum += w;
      }
    }
    const edge = mask ? mask[p] : Math.min(1, wsum * 2);
    if (wsum < 0.05 || edge <= 0) {
      image[o + 3] = 0;
      continue;
    }
    const value = categorical ? values[nearestCells[p]] : sum / wsum;
    const lookupIndex = Math.min(255, Math.max(0, Math.round((value - min) * scale))) * 4;
    image[o] = lut[lookupIndex];
    image[o + 1] = lut[lookupIndex + 1];
    image[o + 2] = lut[lookupIndex + 2];
    image[o + 3] = lut[lookupIndex + 3] * edge;
  }
}

/** The corridor forecast as per-hour Float32Arrays, one per variable. */
export function hourlyArrays(corridor: Corridor): Record<HeatVariable, Float32Array[]> {
  const pack = (rows: number[][]) => rows.map((hour) => Float32Array.from(hour));
  return {
    risk: pack(corridor.risk),
    wind_mph: pack(corridor.wind_mph),
    rain_in_hr: pack(corridor.rain_in_hr),
    snow_in_hr: pack(corridor.snow_in_hr),
  };
}
