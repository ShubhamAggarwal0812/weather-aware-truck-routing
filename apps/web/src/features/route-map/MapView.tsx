import "maplibre-gl/dist/maplibre-gl.css";

import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import {
  type GeoJSONSource,
  type ImageSource,
  type MapLayerMouseEvent,
  Map as MapLibreMap,
  Marker,
  NavigationControl,
  Popup,
  setWorkerUrl,
} from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { HeatmapRenderer, truckAt, useCorridorForecast, useForecastView } from "@/features/forecast";
import { type CheckpointRef, CheckpointDetails, useRouteSelection } from "@/features/route-comparison";
import { usePrefersReducedMotion } from "@/hooks/usePrefersReducedMotion";
import type { Plan } from "@/lib/api/types";
import { EMPTY, checkpointFeatures, planBounds, routeLineFeatures, segmentFeatures, stopFeatures } from "./geojson";
import { HEAT_LAYER, HEAT_SOURCE, addRouteLayers, setRouteFilters } from "./layers";

// MapLibre 6 can't find its worker inside a bundle; Vite hands us a URL for it.
setWorkerUrl(workerUrl);

const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";

/**
 * The MapLibre map, driven imperatively from effects: React owns the data, the map
 * owns rendering. Selection, hover and the forecast hour only touch filters, marker
 * positions and the heatmap image, never the route sources.
 */
export default function MapView({ plan }: { plan: Plan | null }) {
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const [hovered, setHovered] = useState<CheckpointRef | null>(null);
  const popupNode = useMemo(() => document.createElement("div"), []);
  const popup = useRef<Popup | null>(null);
  const trucks = useRef<Map<string, { marker: Marker; el: HTMLDivElement }>>(new Map());
  const heat = useRef<HeatmapRenderer | null>(null);
  const reducedMotion = usePrefersReducedMotion();

  const selectedId = useRouteSelection((s) => s.selectedId);
  const hoveredId = useRouteSelection((s) => s.hoveredId);
  const focus = useRouteSelection((s) => s.focus);
  const hour = useForecastView((s) => s.hour);
  const heatVariable = useForecastView((s) => s.variable);
  const showHeat = useForecastView((s) => s.showHeat);
  const corridor = useCorridorForecast(plan).data ?? null;

  // Create the map once. Handlers read the stores directly, so they never go stale.
  useEffect(() => {
    const map = new MapLibreMap({
      container: container.current!,
      style: STYLE_URL,
      center: [-98.5, 39.5],
      zoom: 3.4,
      dragRotate: false,
      pitchWithRotate: false,
      touchPitch: false,
      attributionControl: { compact: true },
    });
    map.touchZoomRotate.disableRotation();
    map.addControl(new NavigationControl({ showCompass: false }), "top-right");
    map.on("load", () => {
      addRouteLayers(map);
      setReady(true);
    });

    const selection = useRouteSelection.getState;
    const routeId = (e: MapLayerMouseEvent) => e.features?.[0]?.properties?.route as string | undefined;
    const checkpointIndex = (e: MapLayerMouseEvent) => e.features?.[0]?.properties?.index as number | undefined;

    map.on("mousemove", "route-hit", (e) => {
      const id = routeId(e);
      if (id && id !== selection().hoveredId) selection().hover(id);
      map.getCanvas().style.cursor = "pointer";
    });
    map.on("mouseleave", "route-hit", () => {
      selection().hover(null);
      map.getCanvas().style.cursor = "";
    });
    map.on("click", "route-hit", (e) => {
      const id = routeId(e);
      if (id) selection().select(id);
    });
    map.on("mousemove", "checkpoints", (e) => {
      const index = checkpointIndex(e);
      const id = selection().selectedId;
      if (index !== undefined && id) setHovered({ routeId: id, index });
    });
    map.on("mouseleave", "checkpoints", () => setHovered(null));
    map.on("click", "checkpoints", (e) => {
      const index = checkpointIndex(e);
      const id = selection().selectedId;
      if (index !== undefined && id) selection().focusCheckpoint({ routeId: id, index });
    });
    map.on("click", (e) => {
      if (!map.queryRenderedFeatures(e.point, { layers: ["checkpoints"] }).length) selection().focusCheckpoint(null);
    });

    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
    };
  }, []);

  // New plan: route geometry, endpoints, trucks, camera.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    (map.getSource("route-segments") as GeoJSONSource).setData(plan ? segmentFeatures(plan) : EMPTY);
    (map.getSource("route-lines") as GeoJSONSource).setData(plan ? routeLineFeatures(plan) : EMPTY);
    if (!plan) return;

    const first = plan.routes[0];
    const origin = first.checkpoints[0];
    const destination = first.checkpoints[first.checkpoints.length - 1];
    const endpoints = [
      new Marker({ element: endpointElement("origin") }).setLngLat([origin.lon, origin.lat]).addTo(map),
      new Marker({ element: endpointElement("destination") }).setLngLat([destination.lon, destination.lat]).addTo(map),
    ];

    const markers = trucks.current;
    for (const route of plan.routes) {
      const el = document.createElement("div");
      el.className = "truck-marker";
      el.textContent = route.id;
      el.title = `Route ${route.id} truck`;
      const marker = new Marker({ element: el }).setLngLat([origin.lon, origin.lat]).addTo(map);
      markers.set(route.id, { marker, el });
    }

    const narrow = window.innerWidth < 768;
    map.fitBounds(planBounds(plan), {
      padding: narrow ? { top: 40, bottom: 150, left: 24, right: 24 } : { top: 70, bottom: 190, left: 60, right: 60 },
      duration: reducedMotion ? 0 : 900,
    });

    return () => {
      endpoints.forEach((m) => m.remove());
      markers.forEach(({ marker }) => marker.remove());
      markers.clear();
    };
    // The camera moves for a new plan, not for a motion-preference change.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [plan, ready]);

  // Selection and hover only swap layer filters.
  useEffect(() => {
    const map = mapRef.current;
    if (map && ready) setRouteFilters(map, selectedId, hoveredId);
  }, [selectedId, hoveredId, ready]);

  // The selected route's checkpoints and stops.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const route = plan?.routes.find((r) => r.id === selectedId);
    (map.getSource("checkpoints") as GeoJSONSource).setData(checkpointFeatures(route));
    (map.getSource("stops") as GeoJSONSource).setData(stopFeatures(route));
  }, [plan, selectedId, ready]);

  // Focused checkpoint ring, and keep it in view.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    const index = focus && focus.routeId === selectedId ? focus.index : -1;
    map.setFilter("checkpoint-focus", ["==", ["get", "index"], index]);
    const cp = index >= 0 ? plan?.routes.find((r) => r.id === focus!.routeId)?.checkpoints[index] : undefined;
    if (cp && !map.getBounds().contains([cp.lon, cp.lat])) {
      map.easeTo({ center: [cp.lon, cp.lat], duration: reducedMotion ? 0 : 500 });
    }
  }, [focus, selectedId, plan, ready, reducedMotion]);

  // Checkpoint popup: the hovered one wins, otherwise the focused one.
  const shown = hovered ?? focus;
  const shownCheckpoint = useMemo(() => {
    const route = shown && plan?.routes.find((r) => r.id === shown.routeId);
    const checkpoint = route?.checkpoints[shown!.index];
    return route && checkpoint ? { route, checkpoint } : null;
  }, [shown, plan]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (!shownCheckpoint) {
      popup.current?.remove();
      return;
    }
    popup.current ??= new Popup({
      closeButton: false,
      closeOnClick: false,
      maxWidth: "280px",
      offset: 12,
      className: "checkpoint-popup",
    }).setDOMContent(popupNode);
    const { checkpoint } = shownCheckpoint;
    popup.current.setLngLat([checkpoint.lon, checkpoint.lat]).addTo(map);
  }, [shownCheckpoint, ready, popupNode]);

  // Trucks follow the forecast slider.
  useEffect(() => {
    if (!plan) return;
    for (const route of plan.routes) {
      const truck = trucks.current.get(route.id);
      if (!truck) continue;
      const at = truckAt(route.positions, hour);
      truck.marker.setLngLat([at.lon, at.lat]);
      truck.el.dataset.status = at.status;
      truck.el.dataset.selected = String(route.id === selectedId);
    }
  }, [plan, hour, selectedId]);

  // Corridor heatmap: (re)build the image source when new forecast data arrives.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready) return;
    if (map.getLayer(HEAT_LAYER)) map.removeLayer(HEAT_LAYER);
    if (map.getSource(HEAT_SOURCE)) map.removeSource(HEAT_SOURCE);
    heat.current = null;
    if (!corridor || corridor.rows.length === 0) return;

    const renderer = new HeatmapRenderer(corridor, plan?.routes.map((r) => r.corridor_line) ?? []);
    heat.current = renderer;
    map.addSource(HEAT_SOURCE, { type: "image", coordinates: renderer.coordinates });
    const firstLabel = map.getStyle().layers.find((l) => l.type === "symbol")?.id;
    map.addLayer(
      {
        id: HEAT_LAYER,
        type: "raster",
        source: HEAT_SOURCE,
        paint: { "raster-fade-duration": 0, "raster-resampling": "linear", "raster-opacity": 0.9 },
      },
      firstLabel,
    );
    // The corridor query is keyed to the plan, so `plan` is the one it was built from.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [corridor, ready]);

  // Redraw the heatmap for the current layer and (fractional) hour, at most once per frame.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !map.getLayer(HEAT_LAYER)) return;
    map.setLayoutProperty(HEAT_LAYER, "visibility", showHeat ? "visible" : "none");
    if (!showHeat || !heat.current) return;
    const renderer = heat.current;
    const frame = requestAnimationFrame(() => {
      (map.getSource(HEAT_SOURCE) as ImageSource | undefined)?.updateImage({
        image: renderer.draw(heatVariable, hour),
      });
      map.triggerRepaint();
    });
    return () => cancelAnimationFrame(frame);
  }, [corridor, hour, heatVariable, showHeat, ready]);

  return (
    <>
      {/* MapLibre sets position: relative on its container, so it gets a positioned parent. */}
      <div className="absolute inset-0">
        <div ref={container} className="h-full w-full" role="region" aria-label="Route map" />
      </div>
      {shownCheckpoint &&
        createPortal(
          <CheckpointDetails routeId={shownCheckpoint.route.id} checkpoint={shownCheckpoint.checkpoint} compact />,
          popupNode,
        )}
    </>
  );
}

function endpointElement(kind: "origin" | "destination"): HTMLDivElement {
  const el = document.createElement("div");
  el.className = `endpoint-marker endpoint-${kind}`;
  el.title = kind === "origin" ? "Origin" : "Destination";
  return el;
}
