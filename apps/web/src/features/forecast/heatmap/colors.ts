import type { HeatVariable } from "@/lib/api/types";
import { RISK_COLOR } from "@/lib/risk";

export interface Stop {
  value: number;
  color: string;
  alpha: number;
}

export interface Ramp {
  min: number;
  max: number;
  stops: Stop[];
  /** 256 RGBA entries covering [min, max]. */
  lut: Uint8ClampedArray;
}

function hexToRgb(hex: string): [number, number, number] {
  const n = parseInt(hex.slice(1), 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}

export function buildRamp(stops: Stop[]): Ramp {
  const min = stops[0].value;
  const max = stops[stops.length - 1].value;
  const lut = new Uint8ClampedArray(256 * 4);
  let j = 0;
  for (let i = 0; i < 256; i++) {
    const v = min + ((max - min) * i) / 255;
    while (j < stops.length - 2 && v > stops[j + 1].value) j++;
    const a = stops[j];
    const b = stops[j + 1];
    const t = b.value === a.value ? 0 : Math.min(1, Math.max(0, (v - a.value) / (b.value - a.value)));
    const ca = hexToRgb(a.color);
    const cb = hexToRgb(b.color);
    lut[i * 4] = ca[0] + (cb[0] - ca[0]) * t;
    lut[i * 4 + 1] = ca[1] + (cb[1] - ca[1]) * t;
    lut[i * 4 + 2] = ca[2] + (cb[2] - ca[2]) * t;
    lut[i * 4 + 3] = 255 * (a.alpha + (b.alpha - a.alpha) * t);
  }
  return { min, max, stops, lut };
}

// Colour changes land exactly on the spec's thresholds, so the heatmap reads the
// same way as the checkpoint chips (yellow = Moderate, orange = High, ...).
const STOPS: Record<HeatVariable, Stop[]> = {
  risk: [
    { value: 0, color: RISK_COLOR.low, alpha: 0.22 },
    { value: 1, color: RISK_COLOR.moderate, alpha: 0.5 },
    { value: 2, color: RISK_COLOR.high, alpha: 0.6 },
    { value: 3, color: RISK_COLOR.severe, alpha: 0.68 },
    { value: 4, color: RISK_COLOR.no_travel, alpha: 0.75 },
  ],
  wind_mph: [
    { value: 0, color: "#bbf7d0", alpha: 0.0 },
    { value: 12, color: "#86efac", alpha: 0.25 },
    { value: 25, color: RISK_COLOR.moderate, alpha: 0.5 },
    { value: 35, color: RISK_COLOR.high, alpha: 0.6 },
    { value: 45, color: RISK_COLOR.severe, alpha: 0.68 },
    { value: 55, color: RISK_COLOR.no_travel, alpha: 0.75 },
    { value: 65, color: RISK_COLOR.no_travel, alpha: 0.8 },
  ],
  rain_in_hr: [
    { value: 0, color: "#86efac", alpha: 0 },
    { value: 0.005, color: "#86efac", alpha: 0 },
    { value: 0.03, color: "#4ade80", alpha: 0.45 },
    { value: 0.1, color: RISK_COLOR.moderate, alpha: 0.55 },
    { value: 0.25, color: RISK_COLOR.high, alpha: 0.62 },
    { value: 0.5, color: RISK_COLOR.severe, alpha: 0.7 },
    { value: 1.0, color: RISK_COLOR.no_travel, alpha: 0.78 },
    { value: 1.25, color: RISK_COLOR.no_travel, alpha: 0.8 },
  ],
  snow_in_hr: [
    { value: 0, color: "#e0f2fe", alpha: 0 },
    { value: 0.01, color: "#e0f2fe", alpha: 0 },
    { value: 0.1, color: "#7dd3fc", alpha: 0.5 },
    { value: 0.5, color: "#0ea5e9", alpha: 0.58 },
    { value: 1.0, color: "#2563eb", alpha: 0.65 },
    { value: 2.0, color: "#6d28d9", alpha: 0.72 },
    { value: 3.0, color: "#c026d3", alpha: 0.8 },
    { value: 3.5, color: "#c026d3", alpha: 0.8 },
  ],
};

export const RAMPS: Record<HeatVariable, Ramp> = {
  risk: buildRamp(STOPS.risk),
  wind_mph: buildRamp(STOPS.wind_mph),
  rain_in_hr: buildRamp(STOPS.rain_in_hr),
  snow_in_hr: buildRamp(STOPS.snow_in_hr),
};

export const HEAT_LABEL: Record<HeatVariable, string> = {
  risk: "Risk",
  wind_mph: "Wind",
  rain_in_hr: "Rain",
  snow_in_hr: "Snow",
};

export const HEAT_UNIT: Record<HeatVariable, string> = {
  risk: "",
  wind_mph: "mph",
  rain_in_hr: "in/hr",
  snow_in_hr: "in/hr",
};
