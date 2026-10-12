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
import type { Corridor, HeatVariable, Plan } from "../api/types";
import { CheckpointDetails } from "../components/CheckpointDetails";
import { HeatmapRenderer } from "../heatmap/renderer";
import {
  EMPTY,
  checkpointFeatures,
  planBounds,
  routeLineFeatures,
  segmentFeatures,
  stopFeatures,
  truckAt,
} from "./geojson";
import { HEAT_LAYER, HEAT_SOURCE, addRouteLayers, setRouteFilters } from "./layers";

// MapLibre 6 can't find its worker inside a bundle; Vite hands us a URL for it.
setWorkerUrl(workerUrl);

const STYLE_URL = "https://tiles.openfreemap.org/styles/positron";

export interface CheckpointRef {
  routeId: string;
  index: number;
}

interface Props {
  plan: Plan | null;
  corridor: Corridor | null;
  selectedId: string | null;
  hoveredId: string | null;
  hour: number;
  heatVariable: HeatVariable;
  showHeat: boolean;
  focus: CheckpointRef | null;
  onSelectRoute: (id: string) => void;
  onHoverRoute: (id: string | null) => void;
  onFocusCheckpoint: (ref: CheckpointRef | null) => void;
}

const reducedMotion = () => window.matchMedia("(prefers-reduced-motion: reduce)").matches;

export default function MapView(props: Props) {
  const { plan, corridor, selectedId, hoveredId, hour, heatVariable, showHeat, focus } = props;
  const container = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const [ready, setReady] = useState(false);
  const handlers = useRef(props);
  const [hovered, setHovered] = useState<CheckpointRef | null>(null);
  const popupNode = useMemo(() => document.createElement("div"), []);
  const popup = useRef<Popup | null>(null);
  const trucks = useRef<Map<string, { marker: Marker; el: HTMLDivElement }>>(new Map());
  const heat = useRef<HeatmapRenderer | null>(null);

  useEffect(() => {
    handlers.current = props;
  });

  // Create the map once.
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

    const onRouteMove = (e: MapLayerMouseEvent) => {
      const id = e.features?.[0]?.properties?.route as string | undefined;
      if (id) handlers.current.onHoverRoute(id);
      map.getCanvas().style.cursor = "pointer";
    };
    const onRouteLeave = () => {
      handlers.current.onHoverRoute(null);
      map.getCanvas().style.cursor = "";
    };
    const onRouteClick = (e: MapLayerMouseEvent) => {
      const id = e.features?.[0]?.properties?.route as string | undefined;
      if (id) handlers.current.onSelectRoute(id);
    };
    const onCheckpointMove = (e: MapLayerMouseEvent) => {
      const index = e.features?.[0]?.properties?.index as number | undefined;
      const routeId = handlers.current.selectedId;
      if (index !== undefined && routeId) setHovered({ routeId, index });
    };
    const onCheckpointLeave = () => setHovered(null);
    const onCheckpointClick = (e: MapLayerMouseEvent) => {
      const index = e.features?.[0]?.properties?.index as number | undefined;
      const routeId = handlers.current.selectedId;
      if (index !== undefined && routeId) handlers.current.onFocusCheckpoint({ routeId, index });
    };
    const onMapClick = (e: MapLayerMouseEvent) => {
      if (!map.queryRenderedFeatures(e.point, { layers: ["checkpoints"] }).length) {
        handlers.current.onFocusCheckpoint(null);
      }
    };

    map.on("mousemove", "route-hit", onRouteMove);
    map.on("mouseleave", "route-hit", onRouteLeave);
    map.on("click", "route-hit", onRouteClick);
    map.on("mousemove", "checkpoints", onCheckpointMove);
    map.on("mouseleave", "checkpoints", onCheckpointLeave);
    map.on("click", "checkpoints", onCheckpointClick);
    map.on("click", onMapClick);
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
      new Marker({ element: endpointElement("destination") })
        .setLngLat([destination.lon, destination.lat])
        .addTo(map),
    ];

    const markers = trucks.current;
    for (const route of plan.routes) {
      const el = document.createElement("div");
      el.className = "truck-marker";
      el.textContent = route.id;
      el.title = `Route ${route.id} truck position`;
      const marker = new Marker({ element: el }).setLngLat([origin.lon, origin.lat]).addTo(map);
      markers.set(route.id, { marker, el });
    }

    const narrow = window.innerWidth < 768;
    map.fitBounds(planBounds(plan), {
      padding: narrow ? { top: 40, bottom: 150, left: 24, right: 24 } : { top: 70, bottom: 190, left: 60, right: 60 },
      duration: reducedMotion() ? 0 : 900,
    });

    return () => {
      endpoints.forEach((m) => m.remove());
      markers.forEach(({ marker }) => marker.remove());
      markers.clear();
    };
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
    if (index < 0 || !plan) return;
    const cp = plan.routes.find((r) => r.id === focus!.routeId)?.checkpoints[index];
    if (cp && !map.getBounds().contains([cp.lon, cp.lat])) {
      map.easeTo({ center: [cp.lon, cp.lat], duration: reducedMotion() ? 0 : 500 });
    }
  }, [focus, selectedId, plan, ready]);

  // Checkpoint popup: the hovered one wins, otherwise the focused one.
  const shown = hovered ?? focus;
  const shownCheckpoint = useMemo(() => {
    if (!shown || !plan) return null;
    const route = plan.routes.find((r) => r.id === shown.routeId);
    const checkpoint = route?.checkpoints[shown.index];
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

  // Redraw the heatmap for the current variable and (fractional) hour, at most once per frame.
  useEffect(() => {
    const map = mapRef.current;
    if (!map || !ready || !map.getLayer(HEAT_LAYER)) return;
    map.setLayoutProperty(HEAT_LAYER, "visibility", showHeat ? "visible" : "none");
    if (!showHeat || !heat.current) return;
    const renderer = heat.current;
    const frame = requestAnimationFrame(() => {
      (map.getSource(HEAT_SOURCE) as ImageSource | undefined)?.updateImage({ image: renderer.draw(heatVariable, hour) });
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
