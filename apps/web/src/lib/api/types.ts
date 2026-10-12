// Domain names for the generated API types. Regenerate with `make schema`; don't edit by hand.
import type { components } from "../../generated/api";

type Schemas = components["schemas"];

export type RiskKey = Schemas["RiskLevelEnum"];
export type Condition = Schemas["ConditionEnum"];
export type Location = Schemas["Location"];
export type Place = Schemas["Place"];
export type PlanRequest = Schemas["PlanRequest"];
export type Plan = Schemas["Plan"];
export type RoutePlan = Schemas["RoutePlan"];
export type Checkpoint = Schemas["Checkpoint"];
export type Stop = Schemas["Stop"];
export type RiskRules = Schemas["RiskRules"];
export type CorridorRequest = Schemas["CorridorRequest"];
export type Corridor = Schemas["Corridor"];
export type AppConfig = Schemas["Config"];

/** Heatmap layers: the Corridor fields that hold per-hour values. */
export type HeatVariable = "risk" | "wind_mph" | "rain_in_hr" | "snow_in_hr";
