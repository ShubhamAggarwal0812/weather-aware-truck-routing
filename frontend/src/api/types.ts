// Mirrors the Django API (backend/trips/services/planner.py).

export type RiskKey = "low" | "moderate" | "high" | "severe" | "no_travel";
export type Condition = "wind" | "rain" | "snow";

export interface Place {
  label: string;
  lat: number;
  lon: number;
}

export interface PlanRequest {
  origin: Place;
  destination: Place;
  departure: string; // ISO 8601 with offset
  load_weight_lb: number;
  interval_miles: 10 | 25 | 50;
  rest_breaks: boolean;
}

export interface Band {
  level: RiskKey;
  threshold: number;
  inclusive: boolean;
}

export interface RiskRules {
  levels: { key: RiskKey; label: string; score: number }[];
  wind_mph: Band[];
  rain_in_hr: Band[];
  snow_in_hr: Band[];
  load_rules: {
    min_wind_mph: number;
    max_wind_mph: number;
    min_load_lb: number;
    level: RiskKey;
    description: string;
  }[];
}

export interface Checkpoint {
  index: number;
  mile: number;
  covers_mi: [number, number];
  lat: number;
  lon: number;
  eta: string;
  drive_time_s: number;
  level: RiskKey;
  conditions: {
    wind_mph: number;
    gust_mph: number;
    rain_in_hr: number;
    snow_in_hr: number;
    temp_f: number;
  };
  factors: { condition: Condition; level: RiskKey; load_rule: string | null }[];
  drivers: Condition[];
}

export interface Stop {
  kind: "break" | "rest";
  mile: number;
  lat: number;
  lon: number;
  start: string;
  end: string;
}

/** [lat, lon, status]; status: 0 waiting, 1 driving, 2 break, 3 rest, 4 arrived. */
export type Position = [number, number, number];

export interface RoutePlan {
  id: string;
  summary: string;
  rank: number;
  recommended: boolean;
  distance_mi: number;
  drive_time_s: number;
  travel_time_s: number;
  arrival: string;
  notes: string[];
  risk: {
    miles_by_level: Record<RiskKey, number>;
    average: number;
    max_level: RiskKey;
  };
  checkpoints: Checkpoint[];
  segments: { checkpoint: number; level: RiskKey; coordinates: [number, number][] }[];
  stops: Stop[];
  positions: Position[];
  corridor_line: [number, number][];
}

export interface Comparison {
  route_id: string;
  criterion: "no_travel_miles" | "severe_miles" | "high_miles" | "average_risk" | "travel_time" | "tie";
  recommended_value: number;
  other_value: number;
}

export interface Plan {
  provider: { name: string; truck_aware: boolean };
  departure: string;
  load_weight_lb: number;
  gross_weight_lb: number;
  interval_miles: number;
  rest_breaks: boolean;
  heatmap_start: string;
  routes: RoutePlan[];
  recommendation: {
    route_id: string;
    safe: boolean;
    headline: string;
    reasons: string[];
    comparisons: Comparison[];
  };
  rules: RiskRules;
}

export interface CorridorRequest {
  lines: [number, number][][];
  departure: string;
  load_weight_lb: number;
}

export type HeatVariable = "risk" | "wind_mph" | "rain_in_hr" | "snow_in_hr";

export interface Corridor {
  step_deg: number;
  rows: number[];
  cols: number[];
  times: string[];
  wind_mph: number[][];
  rain_in_hr: number[][];
  snow_in_hr: number[][];
  risk: number[][];
}

export interface AppConfig {
  routing_provider: string;
  truck_aware: boolean;
  rules: RiskRules;
}
