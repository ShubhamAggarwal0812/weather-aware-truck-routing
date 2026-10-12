import type { HeatVariable } from "@/lib/api/types";
import { RISK_LABEL, RISK_ORDER } from "@/lib/risk";
import { HEAT_UNIT, RAMPS } from "../heatmap/colors";

const TICKS: Record<Exclude<HeatVariable, "risk">, number[]> = {
  wind_mph: [25, 35, 45, 55],
  rain_in_hr: [0.1, 0.25, 0.5, 1.0],
  snow_in_hr: [0.5, 1, 2, 3],
};

export function HeatLegend({ variable }: { variable: HeatVariable }) {
  const ramp = RAMPS[variable];
  const css = ramp.stops
    .map((s) => {
      const pct = ((s.value - ramp.min) / (ramp.max - ramp.min)) * 100;
      return `${s.color}${Math.round(Math.max(s.alpha, 0.15) * 255)
        .toString(16)
        .padStart(2, "0")} ${pct.toFixed(1)}%`;
    })
    .join(", ");
  const at = (v: number) => `${((v - ramp.min) / (ramp.max - ramp.min)) * 100}%`;

  return (
    <div className="w-full">
      <div
        className="h-2 w-full rounded-full ring-1 ring-black/5"
        style={{ background: `linear-gradient(to right, ${css})` }}
      />
      <div className="relative mt-0.5 h-3.5 text-[10px] text-slate-500">
        {variable === "risk"
          ? RISK_ORDER.map((k, i) => (
              <span
                key={k}
                className="absolute -translate-x-1/2 whitespace-nowrap first:translate-x-0 last:-translate-x-full"
                style={{ left: at(i) }}
              >
                {RISK_LABEL[k]}
              </span>
            ))
          : TICKS[variable].map((v) => (
              <span key={v} className="absolute -translate-x-1/2 tabular-nums" style={{ left: at(v) }}>
                {v}
              </span>
            ))}
        {variable !== "risk" && <span className="absolute right-0 text-slate-400">{HEAT_UNIT[variable]}</span>}
      </div>
    </div>
  );
}
