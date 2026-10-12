import type { Corridor, HeatVariable, RiskRules } from "@/lib/api/types";
import { CATEGORICAL, type Ramp, rampsFor } from "./colors";
import {
  type GridLayout,
  type Sampler,
  buildLayout,
  buildSampler,
  hourlyArrays,
  paint,
  projector,
  valuesAt,
} from "./raster";

const CORRIDOR_MILES = 30;
const METERS_PER_MILE = 1609.344;
const EARTH_RADIUS_M = 6_371_008.8;

/** Paints the corridor forecast into one reusable ImageData for a MapLibre image source. */
export class HeatmapRenderer {
  readonly layout: GridLayout;
  readonly image: ImageData;
  private readonly sampler: Sampler;
  private readonly hours: Record<HeatVariable, Float32Array[]>;
  private readonly scratch: Float32Array;
  private readonly mask: Float32Array | undefined;
  private readonly ramps: Record<HeatVariable, Ramp>;

  /** ``lines`` are the routes as [lat, lon] lists; the heatmap is clipped to a band around them. */
  constructor(corridor: Corridor, lines: number[][][], rules: RiskRules) {
    this.layout = buildLayout(corridor);
    this.sampler = buildSampler(this.layout);
    this.hours = hourlyArrays(corridor);
    this.image = new ImageData(this.sampler.width, this.sampler.height);
    this.scratch = new Float32Array(corridor.rows.length);
    this.mask = corridorMask(this.layout, this.sampler, lines);
    this.ramps = rampsFor(rules);
  }

  /** Corners for a MapLibre image source: top-left, top-right, bottom-right, bottom-left. */
  get coordinates(): [[number, number], [number, number], [number, number], [number, number]] {
    const { west, east, south, north } = this.layout.bounds;
    return [
      [west, north],
      [east, north],
      [east, south],
      [west, south],
    ];
  }

  draw(variable: HeatVariable, hour: number): ImageData {
    const categorical = CATEGORICAL.has(variable);
    // Each hour's risk covers the hour that starts then, as a checkpoint's ETA is scored.
    valuesAt(this.hours[variable], categorical ? Math.floor(hour) : hour, this.scratch);
    paint(this.sampler, this.scratch, this.ramps[variable], this.image.data, this.mask, categorical);
    return this.image;
  }
}

/**
 * A soft-edged band of CORRIDOR_MILES either side of the routes, drawn once with
 * Canvas 2D strokes in image pixels. Without canvas support the grid edge is used.
 */
function corridorMask(layout: GridLayout, sampler: Sampler, lines: number[][][]): Float32Array | undefined {
  const canvas = document.createElement("canvas");
  canvas.width = sampler.width;
  canvas.height = sampler.height;
  const ctx = canvas.getContext("2d", { willReadFrequently: true });
  if (!ctx) return undefined;

  const project = projector(layout, sampler.width, sampler.height);
  const { west, east, south, north } = layout.bounds;
  const midLat = ((south + north) / 2) * (Math.PI / 180);
  // Image pixels per meter at the corridor's middle latitude.
  const pxPerMeter = sampler.width / (((east - west) * Math.PI) / 180) / (EARTH_RADIUS_M * Math.cos(midLat));
  const bufferPx = CORRIDOR_MILES * METERS_PER_MILE * pxPerMeter;

  ctx.filter = `blur(${Math.max(1, bufferPx * 0.15).toFixed(1)}px)`;
  ctx.strokeStyle = "#fff";
  ctx.lineWidth = bufferPx * 1.8;
  ctx.lineCap = "round";
  ctx.lineJoin = "round";
  for (const line of lines) {
    ctx.beginPath();
    line.forEach(([lat, lon], i) => {
      const [x, y] = project(lon, lat);
      if (i === 0) ctx.moveTo(x, y);
      else ctx.lineTo(x, y);
    });
    ctx.stroke();
  }
  const alpha = ctx.getImageData(0, 0, sampler.width, sampler.height).data;
  const mask = new Float32Array(sampler.width * sampler.height);
  for (let i = 0; i < mask.length; i++) mask[i] = alpha[i * 4 + 3] / 255;
  return mask;
}
