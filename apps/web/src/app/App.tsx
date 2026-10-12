import { Suspense, lazy } from "react";
import { ErrorBoundary } from "@/components/ui/ErrorBoundary";
import { Spinner } from "@/components/ui/Spinner";
import { Timeline, useForecastView } from "@/features/forecast";
import { CheckpointList, Recommendation, RouteCards, useRouteSelection } from "@/features/route-comparison";
import { TripForm, usePlanTrip } from "@/features/trip-planner";
import { ApiError, fieldMessages } from "@/lib/api/client";
import type { PlanRequest } from "@/lib/api/types";
import { formatDateTime } from "@/lib/format";

// MapLibre is most of the bundle; the form renders while it loads.
const MapView = lazy(() => import("@/features/route-map/MapView"));

export function App() {
  const planning = usePlanTrip();
  const plan = planning.data ?? null;
  const selectedId = useRouteSelection((s) => s.selectedId);
  const selectedRoute = plan?.routes.find((r) => r.id === selectedId);
  const planError = planning.error instanceof ApiError ? planning.error : null;

  const submit = (request: PlanRequest) =>
    planning.mutate(request, {
      onSuccess: (result) => {
        useRouteSelection.getState().reset(result.recommendation.route_id);
        useForecastView.getState().rewind();
      },
    });

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

          <TripForm loading={planning.isPending} onSubmit={submit} />

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
              <RouteCards plan={plan} />
              {selectedRoute && <CheckpointList route={selectedRoute} intervalMiles={plan.interval_miles} />}
            </div>
          )}
        </div>
      </aside>

      <main className="relative order-1 h-[52dvh] shrink-0 md:order-2 md:h-auto md:flex-1">
        <ErrorBoundary
          fallback={
            <div className="absolute inset-0 flex items-center justify-center p-6 text-center text-sm text-slate-600">
              The map couldn't start. It needs a browser with WebGL2.
            </div>
          }
        >
          <Suspense fallback={<div className="absolute inset-0 animate-pulse bg-slate-200" />}>
            <MapView plan={plan} />
          </Suspense>
        </ErrorBoundary>

        {planning.isPending && (
          <div className="pointer-events-none absolute inset-x-0 top-4 flex justify-center px-4" role="status">
            <div className="flex items-center gap-2 rounded-full bg-slate-900 px-4 py-2 text-xs font-medium text-white shadow-lg">
              <Spinner tone="light" className="h-3.5 w-3.5" />
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
            <Timeline plan={plan} />
          </div>
        )}
      </main>
    </div>
  );
}
