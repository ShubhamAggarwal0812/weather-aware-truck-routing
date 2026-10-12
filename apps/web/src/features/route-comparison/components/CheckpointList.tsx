import { useEffect, useRef } from "react";
import { RiskChip } from "@/components/ui/RiskChip";
import type { RoutePlan } from "@/lib/api/types";
import { formatDayTime, formatDuration, formatRate } from "@/lib/format";
import { RISK_COLOR } from "@/lib/risk";
import { useRouteSelection } from "../store";

interface Props {
  route: RoutePlan;
  intervalMiles: number;
}

type Row = { kind: "checkpoint"; mile: number; index: number } | { kind: "stop"; mile: number; index: number };

function byRouteOrder(first: Row, second: Row): number {
  return (
    first.mile - second.mile ||
    Number(first.kind === "stop") - Number(second.kind === "stop") ||
    first.index - second.index
  );
}

export function CheckpointList({ route, intervalMiles }: Readonly<Props>) {
  const focus = useRouteSelection((s) => s.focus);
  const onFocus = useRouteSelection((s) => s.focusCheckpoint);
  const rows: Row[] = [
    ...route.checkpoints.map((cp) => ({ kind: "checkpoint" as const, mile: cp.mile, index: cp.index })),
    ...route.stops.map((s, i) => ({ kind: "stop" as const, mile: s.mile, index: i })),
  ].sort(byRouteOrder);

  const focused = focus?.routeId === route.id ? focus.index : -1;
  const listRef = useRef<HTMLOListElement>(null);
  useEffect(() => {
    if (focused < 0) return;
    listRef.current
      ?.querySelector(`[data-checkpoint="${focused}"]`)
      ?.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }, [focused]);

  return (
    <section>
      <h2 className="mb-1.5 flex items-baseline justify-between text-sm font-semibold text-slate-900">
        Route {route.id} checkpoints
        <span className="text-xs font-normal text-slate-500">
          {route.checkpoints.length} · every {intervalMiles} mi
        </span>
      </h2>
      <ol ref={listRef} className="divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white text-xs">
        {rows.map((row) => {
          if (row.kind === "stop") {
            const stop = route.stops[row.index];
            const duration = (new Date(stop.end).getTime() - new Date(stop.start).getTime()) / 1000;
            return (
              <li key={`stop-${row.index}`} className="flex items-center gap-2 bg-slate-50 px-3 py-1.5 text-slate-600">
                <span className={`h-2.5 w-2.5 rounded-full ${stop.kind === "rest" ? "bg-blue-900" : "bg-slate-500"}`} />
                <span className="w-12 tabular-nums">mi {Math.round(stop.mile)}</span>
                <span>
                  {stop.kind === "rest" ? "10-hour rest" : "30-minute break"} · {formatDayTime(stop.start)} for{" "}
                  {formatDuration(duration)}
                </span>
              </li>
            );
          }
          const cp = route.checkpoints[row.index];
          const c = cp.conditions;
          const active = cp.index === focused;
          return (
            <li key={`cp-${cp.index}`} data-checkpoint={cp.index}>
              <button
                type="button"
                onClick={() => onFocus(active ? null : { routeId: route.id, index: cp.index })}
                className={`grid w-full grid-cols-[3rem_1fr_auto] items-center gap-2 px-3 py-1.5 text-left transition ${
                  active ? "bg-slate-100" : "hover:bg-slate-50"
                }`}
                aria-pressed={active}
              >
                <span className="flex items-center gap-1.5 tabular-nums text-slate-700">
                  <span className="h-2 w-2 shrink-0 rounded-full" style={{ background: RISK_COLOR[cp.level] }} />
                  {Math.round(cp.mile)}
                </span>
                <span className="min-w-0">
                  <span className="block font-medium text-slate-800">{formatDayTime(cp.eta)}</span>
                  <span className="block truncate tabular-nums text-slate-500">
                    {c.wind_mph.toFixed(0)} mph · rain {formatRate(c.rain_in_hr)} · snow {formatRate(c.snow_in_hr)} ·{" "}
                    {c.temp_f}°F
                  </span>
                </span>
                <RiskChip level={cp.level} size="xs" />
              </button>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
