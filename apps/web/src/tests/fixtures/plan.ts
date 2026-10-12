import type { Checkpoint, Plan, RiskKey, RiskRules, RoutePlan } from "@/lib/api/types";

const NO_MILES = { low: 0, moderate: 0, high: 0, severe: 0, no_travel: 0 };

export const RULES: RiskRules = {
  levels: [
    { key: "low", label: "Low", score: 0 },
    { key: "moderate", label: "Moderate", score: 1 },
    { key: "high", label: "High", score: 2 },
    { key: "severe", label: "Severe", score: 3 },
    { key: "no_travel", label: "No Travel", score: 4 },
  ],
  wind_mph: [
    { level: "moderate", threshold: 25, inclusive: true },
    { level: "high", threshold: 35, inclusive: true },
    { level: "severe", threshold: 45, inclusive: true },
    { level: "no_travel", threshold: 55, inclusive: true },
  ],
  rain_in_hr: [
    { level: "moderate", threshold: 0.1, inclusive: true },
    { level: "high", threshold: 0.25, inclusive: true },
    { level: "severe", threshold: 0.5, inclusive: true },
    { level: "no_travel", threshold: 1.0, inclusive: false },
  ],
  snow_in_hr: [
    { level: "moderate", threshold: 0.5, inclusive: true },
    { level: "high", threshold: 1.0, inclusive: true },
    { level: "severe", threshold: 2.0, inclusive: true },
    { level: "no_travel", threshold: 3.0, inclusive: false },
  ],
  load_rules: [
    {
      min_wind_mph: 45,
      max_wind_mph: 55,
      min_load_lb: 30_000,
      level: "no_travel",
      description: "45-54 mph wind with a load over 30,000 lb",
    },
    {
      min_wind_mph: 35,
      max_wind_mph: 45,
      min_load_lb: 40_000,
      level: "severe",
      description: "35-44 mph wind with a load over 40,000 lb",
    },
  ],
};

export function checkpoint(index: number, level: RiskKey = "low"): Checkpoint {
  return {
    index,
    mile: index * 25,
    covers_mi: [Math.max(0, index * 25 - 12.5), index * 25 + 12.5],
    lat: 40,
    lon: -105 + index * 0.5,
    eta: new Date(Date.UTC(2026, 9, 13, 12 + index)).toISOString(),
    drive_time_s: index * 1500,
    level,
    conditions: { wind_mph: 38.2, gust_mph: 51, rain_in_hr: 0, snow_in_hr: 0, temp_f: 41 },
    factors: [
      { condition: "wind", level, load_rule: level === "severe" ? "35-44 mph wind with a load over 40,000 lb" : null },
      { condition: "rain", level: "low", load_rule: null },
      { condition: "snow", level: "low", load_rule: null },
    ],
    drivers: level === "low" ? [] : ["wind"],
  };
}

export function route(id: string, overrides: Partial<RoutePlan> = {}): RoutePlan {
  return {
    id,
    summary: `via I-${id.charCodeAt(0)}`,
    rank: 1,
    recommended: false,
    distance_mi: 1006,
    drive_time_s: 50_000,
    travel_time_s: 52_000,
    arrival: "2026-10-14T02:00:00Z",
    notes: [],
    risk: { miles_by_level: { ...NO_MILES, low: 1006 }, average: 0, max_level: "low" },
    checkpoints: [checkpoint(0), checkpoint(1)],
    segments: [],
    stops: [],
    positions: [
      [40, -105, 0],
      [40, -104, 1],
    ],
    corridor_line: [
      [40, -105],
      [40, -95],
    ],
    ...overrides,
  };
}

export function plan(overrides: Partial<Plan> = {}): Plan {
  return {
    provider: { name: "tomtom", truck_aware: true },
    departure: "2026-10-13T12:20:00Z",
    load_weight_lb: 42_000,
    gross_weight_lb: 77_000,
    interval_miles: 25,
    rest_breaks: true,
    heatmap_start: "2026-10-13T12:00:00Z",
    routes: [
      route("A", {
        rank: 2,
        risk: { miles_by_level: { ...NO_MILES, low: 970, severe: 36 }, average: 0.11, max_level: "severe" },
      }),
      route("B", { rank: 1, recommended: true }),
    ],
    recommendation: {
      route_id: "B",
      safe: true,
      headline: "Route B is the safest option.",
      reasons: ["Fewer Severe miles than Route A (0 vs 36 mi)."],
      comparisons: [{ route_id: "A", criterion: "severe_miles", recommended_value: 0, other_value: 36 }],
    },
    rules: RULES,
    ...overrides,
  };
}
