import type { ExpressionSpecification, Map as MapLibreMap } from "maplibre-gl";
import { RISK_COLOR } from "@/lib/risk";
import { EMPTY } from "./geojson";

export const HEAT_SOURCE = "corridor-heat";
export const HEAT_LAYER = "corridor-heat";

const riskColor: ExpressionSpecification = [
  "match",
  ["get", "level"],
  "low",
  RISK_COLOR.low,
  "moderate",
  RISK_COLOR.moderate,
  "high",
  RISK_COLOR.high,
  "severe",
  RISK_COLOR.severe,
  "no_travel",
  RISK_COLOR.no_travel,
  "#64748b",
];

const byZoom = (z4: number, z10: number): ExpressionSpecification => [
  "interpolate",
  ["linear"],
  ["zoom"],
  4,
  z4,
  10,
  z10,
];

const NONE = "__none__";

/** Static layers, added once. Selection and hover only swap filters, never data. */
export function addRouteLayers(map: MapLibreMap): void {
  for (const id of ["route-segments", "route-lines", "checkpoints", "stops"]) {
    map.addSource(id, { type: "geojson", data: EMPTY });
  }
  const round = { "line-join": "round", "line-cap": "round" } as const;

  map.addLayer({
    id: "route-hover",
    type: "line",
    source: "route-lines",
    filter: ["==", ["get", "route"], NONE],
    layout: round,
    paint: { "line-color": "#0f172a", "line-opacity": 0.22, "line-width": byZoom(11, 18), "line-blur": 2 },
  });
  map.addLayer({
    id: "route-casing-other",
    type: "line",
    source: "route-lines",
    layout: round,
    paint: { "line-color": "#ffffff", "line-width": byZoom(5, 9), "line-opacity": 0.9 },
  });
  map.addLayer({
    id: "route-line-other",
    type: "line",
    source: "route-segments",
    layout: round,
    paint: { "line-color": riskColor, "line-width": byZoom(2.5, 5), "line-opacity": 0.5 },
  });
  map.addLayer({
    id: "route-casing-selected",
    type: "line",
    source: "route-lines",
    filter: ["==", ["get", "route"], NONE],
    layout: round,
    paint: { "line-color": "#0f172a", "line-width": byZoom(7.5, 13), "line-opacity": 0.85 },
  });
  map.addLayer({
    id: "route-line-selected",
    type: "line",
    source: "route-segments",
    filter: ["==", ["get", "route"], NONE],
    layout: round,
    paint: { "line-color": riskColor, "line-width": byZoom(4.5, 8.5) },
  });
  map.addLayer({
    id: "route-hit",
    type: "line",
    source: "route-lines",
    layout: round,
    paint: { "line-color": "#000000", "line-opacity": 0, "line-width": 18 },
  });
  map.addLayer({
    id: "stops",
    type: "circle",
    source: "stops",
    paint: {
      "circle-radius": byZoom(4, 7),
      "circle-color": ["match", ["get", "kind"], "rest", "#1e3a8a", "#475569"],
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 2,
    },
  });
  map.addLayer({
    id: "checkpoint-focus",
    type: "circle",
    source: "checkpoints",
    filter: ["==", ["get", "index"], -1],
    paint: {
      "circle-radius": byZoom(10, 15),
      "circle-color": "rgba(0,0,0,0)",
      "circle-stroke-color": "#0f172a",
      "circle-stroke-width": 3,
    },
  });
  map.addLayer({
    id: "checkpoints",
    type: "circle",
    source: "checkpoints",
    paint: {
      "circle-radius": byZoom(4, 8),
      "circle-color": riskColor,
      "circle-stroke-color": "#ffffff",
      "circle-stroke-width": 1.5,
    },
  });
}

export function setRouteFilters(map: MapLibreMap, selectedId: string | null, hoveredId: string | null): void {
  const selected = selectedId ?? NONE;
  const isSelected: ExpressionSpecification = ["==", ["get", "route"], selected];
  const notSelected: ExpressionSpecification = ["!=", ["get", "route"], selected];
  map.setFilter("route-casing-other", notSelected);
  map.setFilter("route-line-other", notSelected);
  map.setFilter("route-casing-selected", isSelected);
  map.setFilter("route-line-selected", isSelected);
  map.setFilter(
    "route-hover",
    hoveredId && hoveredId !== selectedId ? ["==", ["get", "route"], hoveredId] : ["==", ["get", "route"], NONE],
  );
}
