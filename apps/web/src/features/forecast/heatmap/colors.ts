import type { HeatVariable, RiskKey, RiskRules } from "@/lib/api/types";
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

export const CATEGORICAL: ReadonlySet<HeatVariable> = new Set<HeatVariable>(["risk"]);

function hexToRgb(hex: string): [number, number, number] {
  const packed = Number.parseInt(hex.slice(1), 16);
  return [(packed >> 16) & 255, (packed >> 8) & 255, packed & 255];
}

export function buildRamp(stops: Stop[]): Ramp {
  const min = stops[0].value;
  const max = (stops.at(-1) ?? stops[0]).value;
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

type Look = Omit<Stop, "value">;
type Band = RiskRules["wind_mph"][number];

interface BandLayer {
  below: Stop[];
  levels: Record<Exclude<RiskKey, "low">, Look>;
  headroom: number;
  topAlpha: number;
}

const risk = (key: RiskKey, alpha: number): Look => ({ color: RISK_COLOR[key], alpha });

const RISK_LOOK: Record<RiskKey, Look> = {
  low: risk("low", 0.22),
  moderate: risk("moderate", 0.5),
  high: risk("high", 0.6),
  severe: risk("severe", 0.68),
  no_travel: risk("no_travel", 0.75),
};

// Matches the checkpoint chips, so the heatmap reads the same way.
const BAND_LAYERS: Record<Exclude<HeatVariable, "risk">, BandLayer> = {
  wind_mph: {
    below: [
      { value: 0, color: "#bbf7d0", alpha: 0.0 },
      { value: 12, color: "#86efac", alpha: 0.25 },
    ],
    levels: {
      moderate: risk("moderate", 0.5),
      high: risk("high", 0.6),
      severe: risk("severe", 0.68),
      no_travel: risk("no_travel", 0.75),
    },
    headroom: 10,
    topAlpha: 0.8,
  },
  rain_in_hr: {
    below: [
      { value: 0, color: "#86efac", alpha: 0 },
      { value: 0.005, color: "#86efac", alpha: 0 },
      { value: 0.03, color: "#4ade80", alpha: 0.45 },
    ],
    levels: {
      moderate: risk("moderate", 0.55),
      high: risk("high", 0.62),
      severe: risk("severe", 0.7),
      no_travel: risk("no_travel", 0.78),
    },
    headroom: 0.25,
    topAlpha: 0.8,
  },
  snow_in_hr: {
    below: [
      { value: 0, color: "#e0f2fe", alpha: 0 },
      { value: 0.01, color: "#e0f2fe", alpha: 0 },
      { value: 0.1, color: "#7dd3fc", alpha: 0.5 },
    ],
    levels: {
      moderate: { color: "#0ea5e9", alpha: 0.58 },
      high: { color: "#2563eb", alpha: 0.65 },
      severe: { color: "#6d28d9", alpha: 0.72 },
      no_travel: { color: "#c026d3", alpha: 0.8 },
    },
    headroom: 0.5,
    topAlpha: 0.8,
  },
};

function bandStops(layer: BandLayer, bands: Band[]): Stop[] {
  const first = bands.length ? bands[0].threshold : Infinity;
  const stops = layer.below.filter((stop) => stop.value < first);
  for (const band of bands) {
    if (band.level !== "low") stops.push({ value: band.threshold, ...layer.levels[band.level] });
  }
  const top = stops.at(-1);
  if (top) stops.push({ value: top.value + layer.headroom, color: top.color, alpha: layer.topAlpha });
  return stops;
}

export function levelStops(rules: RiskRules): Stop[] {
  return rules.levels.map((level) => ({ value: level.score, ...RISK_LOOK[level.key] }));
}

function hardEdges(stops: Stop[]): Stop[] {
  return stops.flatMap((stop, index) => {
    if (index === 0) return [stop];
    const previous = stops[index - 1];
    const boundary = (previous.value + stop.value) / 2;
    return [{ ...previous, value: boundary }, { ...stop, value: boundary }, stop];
  });
}

const ramps = new WeakMap<RiskRules, Record<HeatVariable, Ramp>>();

export function rampsFor(rules: RiskRules): Record<HeatVariable, Ramp> {
  let built = ramps.get(rules);
  if (!built) {
    built = {
      risk: buildRamp(hardEdges(levelStops(rules))),
      wind_mph: buildRamp(bandStops(BAND_LAYERS.wind_mph, rules.wind_mph)),
      rain_in_hr: buildRamp(bandStops(BAND_LAYERS.rain_in_hr, rules.rain_in_hr)),
      snow_in_hr: buildRamp(bandStops(BAND_LAYERS.snow_in_hr, rules.snow_in_hr)),
    };
    ramps.set(rules, built);
  }
  return built;
}

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
