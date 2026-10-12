import { useMutation, useQuery } from "@tanstack/react-query";
import { Suspense, lazy, useCallback, useState } from "react";
import { ApiError, api, fieldMessages } from "./api/client";
import type { HeatVariable, Plan } from "./api/types";
import { CheckpointList } from "./components/CheckpointList";
import { Recommendation } from "./components/Recommendation";
import { RouteCards } from "./components/RouteCards";
import { Timeline } from "./components/Timeline";
import { TripForm } from "./components/TripForm";
import { formatDateTime } from "./lib/format";
import type { CheckpointRef } from "./map/MapView";

const MapView = lazy(() => import("./map/MapView"));

export default function App() {
  const [planId, setPlanId] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [hoveredId, setHoveredId] = useState<string | null>(null);
  const [focus, setFocus] = useState<CheckpointRef | null>(null);
  const [hour, setHour] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [heatVariable, setHeatVariable] = useState<HeatVariable>("risk");
  const [showHeat, setShowHeat] = useState(true);

  const planning = useMutation({
    mutationFn: api.plan,
    onSuccess: (result: Plan) => {
      setPlanId((n) => n + 1);
      setSelectedId(result.recommendation.route_id);
      setFocus(null);
      setHour(0);
      setPlaying(false);
    },
  });
  const plan = planning.data ?? null;

  const corridor = useQuery({
    queryKey: ["corridor", planId],
    enabled: plan !== null,
    staleTime: Infinity,
    retry: 1,
    queryFn: ({ signal }) =>
      api.corridor(
        {
          lines: plan!.routes.map((r) => r.corridor_line),
          departure: plan!.departure,
          load_weight_lb: plan!.load_weight_lb,
        },
        signal,
      ),
  });

  const selectRoute = useCallback((id: string) => {
    setSelectedId(id);
    setFocus(null);
  }, []);

  const selectedRoute = plan?.routes.find((r) => r.id === selectedId);
  const planError = planning.error instanceof ApiError ? planning.error : null;

  return (
    <div className="flex h-dvh flex-col bg-slate-100 md:flex-row">
      <aside className="order-2 flex min-h-0 flex-1 flex-col border-slate-200 bg-slate-50 md:order-1 md:w-[420px] md:flex-none md:border-r">
        <div className="min-h-0 flex-1 space-y-4 overflow-y-auto p-4">
          <header>
            <h1 className="text-lg font-bold tracking-tight text-slate-900">Weather-Aware Truck Routing</h1>
            <p className="text-xs text-slate-500">
              Three routes, weather at each checkpoint's ETA, and load-aware risk to pick the safest one.
            </p>
          </header>

          <TripForm loading={planning.isPending} onSubmit={(req) => planning.mutate(req)} />

          {planning.isError && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
              {planError?.message ?? "Something went wrong."}
              {fieldMessages(planError?.fields).map((m) => (
                <div key={m} className="text-xs">
                  {m}
                </div>
              ))}
            </div>
          )}

          {plan && (
            <div className={`space-y-4 transition-opacity ${planning.isPending ? "opacity-50" : ""}`}>
              <div className="text-[11px] text-slate-500">
                Departing {formatDateTime(plan.departure)} · {plan.load_weight_lb.toLocaleString()} lb load (
                {plan.gross_weight_lb.toLocaleString()} lb gross)
              </div>
              {!plan.provider.truck_aware && (
                <p className="rounded-lg bg-amber-50 px-3 py-2 text-xs text-amber-900">
                  Demo routing: the OSRM car profile is in use, so roads and times aren't truck-specific. Set
                  TOMTOM_API_KEY on the server for truck routing.
                </p>
              )}
              <Recommendation plan={plan} />
              <RouteCards
                plan={plan}
                selectedId={selectedId}
                hoveredId={hoveredId}
                onSelect={selectRoute}
                onHover={setHoveredId}
              />
              {selectedRoute && (
                <CheckpointList
                  route={selectedRoute}
                  intervalMiles={plan.interval_miles}
                  focus={focus}
                  onFocus={setFocus}
                />
              )}
            </div>
          )}
        </div>
      </aside>

      <main className="relative order-1 h-[52dvh] shrink-0 md:order-2 md:h-auto md:flex-1">
        <Suspense fallback={<div className="absolute inset-0 animate-pulse bg-slate-200" />}>
          <MapView
            plan={plan}
            corridor={corridor.data ?? null}
            selectedId={selectedId}
            hoveredId={hoveredId}
            hour={hour}
            heatVariable={heatVariable}
            showHeat={showHeat}
            focus={focus}
            onSelectRoute={selectRoute}
            onHoverRoute={setHoveredId}
            onFocusCheckpoint={setFocus}
          />
        </Suspense>

        {planning.isPending && (
          <div className="pointer-events-none absolute inset-x-0 top-4 flex justify-center px-4" role="status">
            <div className="flex items-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-xs font-medium text-white shadow-lg">
              <span className="h-3.5 w-3.5 animate-spin rounded-full border-2 border-white/30 border-t-white" />
              Routing, then checking the forecast at every checkpoint…
            </div>
          </div>
        )}

        {!plan && !planning.isPending && (
          <div className="pointer-events-none absolute inset-x-0 bottom-6 flex justify-center px-4">
            <div className="rounded-full bg-white/90 px-4 py-2 text-xs text-slate-600 shadow">
              Enter a trip to compare routes and see the 48-hour weather along them.
            </div>
          </div>
        )}

        {plan && (
          <div className="pointer-events-none absolute inset-x-2 bottom-2 md:inset-x-auto md:bottom-4 md:left-1/2 md:w-[640px] md:-translate-x-1/2">
            <Timeline
              start={plan.heatmap_start}
              departure={plan.departure}
              hour={hour}
              onHour={setHour}
              playing={playing}
              onPlaying={setPlaying}
              variable={heatVariable}
              onVariable={setHeatVariable}
              showHeat={showHeat}
              onShowHeat={setShowHeat}
              heatStatus={corridor.isPending ? "loading" : corridor.isError ? "error" : "ready"}
              heatError={corridor.error?.message}
              route={selectedRoute}
            />
          </div>
        )}
      </main>
    </div>
  );
}
