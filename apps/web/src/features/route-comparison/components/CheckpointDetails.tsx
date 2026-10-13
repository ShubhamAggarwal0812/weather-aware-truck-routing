import { RiskChip } from "@/components/ui/RiskChip";
import type { Checkpoint, Condition } from "@/lib/api/types";
import { formatDayTime, formatRate } from "@/lib/format";
import { CONDITION_LABEL, RISK_COLOR } from "@/lib/risk";

function conditionValue(checkpoint: Checkpoint, condition: Condition): string {
  const conditions = checkpoint.conditions;
  if (condition === "wind")
    return conditions.gust_mph === null
      ? `${conditions.wind_mph.toFixed(1)} mph`
      : `${conditions.wind_mph.toFixed(1)} mph (gusts ${Math.round(conditions.gust_mph)})`;
  if (condition === "rain") return `${formatRate(conditions.rain_in_hr)} in/hr`;
  return `${formatRate(conditions.snow_in_hr)} in/hr`;
}

export function CheckpointDetails({
  routeId,
  checkpoint,
  compact = false,
}: Readonly<{
  routeId: string;
  checkpoint: Checkpoint;
  compact?: boolean;
}>) {
  const loadRule = checkpoint.factors.find((factor) => factor.load_rule)?.load_rule;
  return (
    <div className={compact ? "text-xs" : "text-sm"}>
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="font-semibold text-slate-900">
            Route {routeId} · mile {Math.round(checkpoint.mile)}
          </div>
          <div className="text-slate-500">ETA {formatDayTime(checkpoint.eta)}</div>
        </div>
        <RiskChip level={checkpoint.level} />
      </div>
      <dl className="mt-2 grid grid-cols-[auto_1fr] gap-x-3 gap-y-1">
        {checkpoint.factors.map((factor) => (
          <div key={factor.condition} className="contents">
            <dt className="flex items-center gap-1.5 text-slate-500">
              <span className="h-2 w-2 rounded-full" style={{ background: RISK_COLOR[factor.level] }} aria-hidden />
              {CONDITION_LABEL[factor.condition]}
            </dt>
            <dd
              className={`tabular-nums ${checkpoint.drivers.includes(factor.condition) ? "font-semibold text-slate-900" : "text-slate-700"}`}
            >
              {conditionValue(checkpoint, factor.condition)}
            </dd>
          </div>
        ))}
        <dt className="text-slate-500 pl-3.5">Temp</dt>
        <dd className="tabular-nums text-slate-700">
          {checkpoint.conditions.temp_f === null ? "Not forecast" : `${checkpoint.conditions.temp_f}°F`}
        </dd>
      </dl>
      {loadRule && <p className="mt-2 rounded bg-amber-50 px-2 py-1 text-amber-900">Load rule: {loadRule}.</p>}
    </div>
  );
}
