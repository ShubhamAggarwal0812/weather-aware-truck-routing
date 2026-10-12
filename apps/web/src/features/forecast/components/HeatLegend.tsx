import type { HeatVariable, RiskRules } from "@/lib/api/types";
import { HEAT_UNIT, levelStops, rampsFor } from "../heatmap/colors";

const swatch = (color: string, alpha: number) =>
  `${color}${Math.round(Math.max(alpha, 0.15) * 255)
    .toString(16)
    .padStart(2, "0")}`;

export function HeatLegend({ variable, rules }: Readonly<{ variable: HeatVariable; rules: RiskRules }>) {
  const ramp = rampsFor(rules)[variable];
  const positionOf = (value: number) => `${((value - ramp.min) / (ramp.max - ramp.min)) * 100}%`;
  const blockWidth = 100 / rules.levels.length;
  const css =
    variable === "risk"
      ? levelStops(rules)
          .map((stop, index) => `${swatch(stop.color, stop.alpha)} ${index * blockWidth}% ${(index + 1) * blockWidth}%`)
          .join(", ")
      : ramp.stops.map((stop) => `${swatch(stop.color, stop.alpha)} ${positionOf(stop.value)}`).join(", ");

  return (
    <div className="w-full">
      <div
        className="h-2 w-full rounded-full ring-1 ring-black/5"
        style={{ background: `linear-gradient(to right, ${css})` }}
      />
      <div className="relative mt-0.5 h-3.5 text-[10px] text-slate-500">
        {variable === "risk"
          ? rules.levels.map((level, index) => (
              <span
                key={level.key}
                className="absolute -translate-x-1/2 whitespace-nowrap"
                style={{ left: `${(index + 0.5) * blockWidth}%` }}
              >
                {level.label}
              </span>
            ))
          : rules[variable].map((band) => (
              <span
                key={band.level}
                className="absolute -translate-x-1/2 tabular-nums"
                style={{ left: positionOf(band.threshold) }}
              >
                {band.threshold}
              </span>
            ))}
        {variable !== "risk" && <span className="absolute right-0 text-slate-400">{HEAT_UNIT[variable]}</span>}
      </div>
    </div>
  );
}
