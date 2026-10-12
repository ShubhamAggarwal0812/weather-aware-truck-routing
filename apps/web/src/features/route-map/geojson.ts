import type { Feature, FeatureCollection, LineString, Point } from "geojson";
import type { Plan, RoutePlan } from "@/lib/api/types";

type LineFeature = Feature<LineString, Record<string, string | number>>;
type PointFeature = Feature<Point, Record<string, string | number>>;

export const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

/** One coloured line per checkpoint stretch: the risk-coloured route. */
export function segmentFeatures(plan: Plan): FeatureCollection {
  const features: LineFeature[] = [];
  for (const route of plan.routes) {
    for (const seg of route.segments) {
      if (seg.coordinates.length < 2) continue;
      features.push({
        type: "Feature",
        geometry: { type: "LineString", coordinates: seg.coordinates },
        properties: { route: route.id, level: seg.level, checkpoint: seg.checkpoint },
      });
    }
  }
  return { type: "FeatureCollection", features };
}

/** Whole routes as single lines: casings, hover halos and the hit area. */
export function routeLineFeatures(plan: Plan): FeatureCollection {
  const features: LineFeature[] = plan.routes.map((route) => ({
    type: "Feature",
    geometry: { type: "LineString", coordinates: fullLine(route) },
    properties: { route: route.id },
  }));
  return { type: "FeatureCollection", features };
}

export function fullLine(route: RoutePlan): number[][] {
  const out: number[][] = [];
  for (const seg of route.segments) {
    // Consecutive segments share their joining point.
    out.push(...(out.length ? seg.coordinates.slice(1) : seg.coordinates));
  }
  return out;
}

export function checkpointFeatures(route: RoutePlan | undefined): FeatureCollection {
  if (!route) return EMPTY;
  const features: PointFeature[] = route.checkpoints.map((cp) => ({
    type: "Feature",
    id: cp.index,
    geometry: { type: "Point", coordinates: [cp.lon, cp.lat] },
    properties: { index: cp.index, level: cp.level },
  }));
  return { type: "FeatureCollection", features };
}

export function stopFeatures(route: RoutePlan | undefined): FeatureCollection {
  if (!route) return EMPTY;
  const features: PointFeature[] = route.stops.map((s, i) => ({
    type: "Feature",
    id: i,
    geometry: { type: "Point", coordinates: [s.lon, s.lat] },
    properties: { kind: s.kind },
  }));
  return { type: "FeatureCollection", features };
}

export function planBounds(plan: Plan): [[number, number], [number, number]] {
  let west = Infinity;
  let south = Infinity;
  let east = -Infinity;
  let north = -Infinity;
  for (const route of plan.routes) {
    for (const [lat, lon] of route.corridor_line) {
      west = Math.min(west, lon);
      east = Math.max(east, lon);
      south = Math.min(south, lat);
      north = Math.max(north, lat);
    }
  }
  return [
    [west, south],
    [east, north],
  ];
}
