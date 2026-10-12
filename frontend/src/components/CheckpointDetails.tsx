import type { Checkpoint, Condition } from "../api/types";
import { formatDayTime, formatRate } from "../lib/format";
import { CONDITION_LABEL, RISK_COLOR } from "../lib/risk";
import { RiskChip } from "./RiskChip";

function conditionValue(cp: Checkpoint, condition: Condition): string {
  const c = cp.conditions;
  if (condition === "wind") return `${c.wind_mph.toFixed(1)} mph (gusts ${Math.round(c.gust_mph)})`;
  if (condition === "rain") return `${formatRate(c.rain_in_hr)} in/hr`;
  return `${formatRate(c.snow_in_hr)} in/hr`;
}

export function CheckpointDetails({
  routeId,
  checkpoint: cp,
  compact = false,
}: {
  routeId: string;
  checkpoint: Checkpoint;
  compact?: boolean;
}) {
  const loadRule = cp.factors.find((f) => f.load_rule)?.load_rule;
  return (
    <div className={compact ? "text-xs" : "text-sm"}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="font-semibold text-slate-900">
            Route {routeId} · mile {Math.round(cp.mile)}
          </div>
          <div className="text-slate-500">ETA {formatDayTime(cp.eta)}</div>
        </div>
        <RiskChip level={cp.level} />
      </div>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        {cp.factors.map((f) => (
          <div key={f.condition} className="contents">
            <dt className="flex items-center gap-1.5 text-slate-500">
              <span className="h-2 w-2 rounded-full" style={{ background: RISK_COLOR[f.level] }} aria-hidden />
              {CONDITION_LABEL[f.condition]}
            </dt>
            <dd className={`tabular-nums ${cp.drivers.includes(f.condition) ? "font-semibold text-slate-900" : "text-slate-700"}`}>
              {conditionValue(cp, f.condition)}
            </dd>
          </div>
        ))}
        <dt className="text-slate-500 pl-3.5">Temp</dt>
        <dd className="tabular-nums text-slate-700">{cp.conditions.temp_f}°F</dd>
      </dl>
      {loadRule && (
        <p className="mt-2 rounded bg-amber-50 px-2 py-1 text-amber-900">Load rule: {loadRule}.</p>
      )}
    </div>
  );
}
