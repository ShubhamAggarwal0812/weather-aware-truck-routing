import { memo } from "react";
import type { Plan, RoutePlan } from "../api/types";
import { formatDayTime, formatDuration, formatMiles } from "../lib/format";
import { RiskBar } from "./RiskBar";
import { RiskChip } from "./RiskChip";

interface Props {
  plan: Plan;
  selectedId: string | null;
  hoveredId: string | null;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
}

export const RouteCards = memo(function RouteCards({ plan, selectedId, hoveredId, onSelect, onHover }: Props) {
  return (
    <div className="space-y-2" role="radiogroup" aria-label="Route options">
      {plan.routes.map((route) => (
        <RouteCard
          key={route.id}
          route={route}
          selected={route.id === selectedId}
          hovered={route.id === hoveredId}
          onSelect={onSelect}
          onHover={onHover}
        />
      ))}
      {plan.routes.length < 3 && (
        <p className="text-xs text-slate-500">
          Only {plan.routes.length} distinct route{plan.routes.length === 1 ? "" : "s"} exist for this trip.
        </p>
      )}
    </div>
  );
});

function RouteCard({
  route,
  selected,
  hovered,
  onSelect,
  onHover,
}: {
  route: RoutePlan;
  selected: boolean;
  hovered: boolean;
  onSelect: (id: string) => void;
  onHover: (id: string | null) => void;
}) {
  const m = route.risk.miles_by_level;
  const breaks = route.travel_time_s - route.drive_time_s;
  return (
    <button
      type="button"
      role="radio"
      aria-checked={selected}
      onClick={() => onSelect(route.id)}
      onMouseEnter={() => onHover(route.id)}
      onMouseLeave={() => onHover(null)}
      onFocus={() => onHover(route.id)}
      onBlur={() => onHover(null)}
      className={`w-full rounded-xl border bg-white p-3 text-left transition ${
        selected
          ? "border-slate-900 ring-1 ring-slate-900"
          : hovered
            ? "border-slate-400"
            : "border-slate-200 hover:border-slate-300"
      }`}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-slate-900 text-xs font-bold text-white">
              {route.id}
            </span>
            <span className="truncate text-sm font-semibold text-slate-900">{route.summary || `Route ${route.id}`}</span>
          </div>
        </div>
        {route.recommended ? (
          <span className="shrink-0 rounded-full bg-emerald-600 px-2 py-0.5 text-[11px] font-semibold text-white">
            Recommended
          </span>
        ) : (
          <span className="shrink-0 text-[11px] font-medium text-slate-400">#{route.rank}</span>
        )}
      </div>

      <dl className="mt-2 grid grid-cols-3 gap-2 text-xs">
        <div>
          <dt className="text-slate-500">Distance</dt>
          <dd className="font-semibold tabular-nums text-slate-900">{formatMiles(route.distance_mi)}</dd>
        </div>
        <div>
          <dt className="text-slate-500">Trip time</dt>
          <dd className="font-semibold tabular-nums text-slate-900">{formatDuration(route.travel_time_s)}</dd>
          {breaks > 0 && <dd className="text-[10px] text-slate-500">incl. {formatDuration(breaks)} stops</dd>}
        </div>
        <div>
          <dt className="text-slate-500">Arrives</dt>
          <dd className="font-semibold tabular-nums text-slate-900">{formatDayTime(route.arrival)}</dd>
        </div>
      </dl>

      <div className="mt-2.5">
        <RiskBar miles={m} />
        <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-slate-600 tabular-nums">
          <span className="flex items-center gap-1">
            Worst <RiskChip level={route.risk.max_level} size="xs" />
          </span>
          {m.no_travel > 0 && <span className="font-semibold text-purple-700">No Travel {Math.round(m.no_travel)} mi</span>}
          <span>Severe {Math.round(m.severe)} mi</span>
          <span>High {Math.round(m.high)} mi</span>
          <span title="Distance-weighted, Low = 0 to No Travel = 4">Avg risk {route.risk.average.toFixed(2)}/4</span>
        </div>
      </div>
      {route.notes.map((n) => (
        <p key={n} className="mt-1.5 text-[11px] text-slate-400">
          {n}
        </p>
      ))}
    </button>
  );
}
