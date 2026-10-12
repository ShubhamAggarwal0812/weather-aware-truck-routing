import type { Condition, RiskKey } from "../api/types";

export const RISK_ORDER: RiskKey[] = ["low", "moderate", "high", "severe", "no_travel"];

export const RISK_LABEL: Record<RiskKey, string> = {
  low: "Low",
  moderate: "Moderate",
  high: "High",
  severe: "Severe",
  no_travel: "No Travel",
};

/** One palette for map lines, checkpoints, chips and the risk heatmap. */
export const RISK_COLOR: Record<RiskKey, string> = {
  low: "#16a34a",
  moderate: "#eab308",
  high: "#f97316",
  severe: "#dc2626",
  no_travel: "#7e22ce",
};

export const RISK_TEXT_ON: Record<RiskKey, string> = {
  low: "#ffffff",
  moderate: "#1c1917",
  high: "#1c1917",
  severe: "#ffffff",
  no_travel: "#ffffff",
};

export const CONDITION_LABEL: Record<Condition, string> = { wind: "Wind", rain: "Rain", snow: "Snow" };
