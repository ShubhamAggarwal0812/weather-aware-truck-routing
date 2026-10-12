import { useEffect, useRef } from "react";
import type { HeatVariable, RoutePlan } from "../api/types";
import { HEAT_LABEL } from "../heatmap/colors";
import { formatDayTime } from "../lib/format";
import { truckAt } from "../map/geojson";
import { HeatLegend } from "./HeatLegend";

export const HOURS = 48;
const PLAY_HOURS_PER_SECOND = 3;
const VARIABLES: HeatVariable[] = ["risk", "wind_mph", "rain_in_hr", "snow_in_hr"];
const STATUS_TEXT = {
  waiting: "not departed",
  driving: "driving",
  break: "on a 30-min break",
  rest: "on a 10-h rest",
  arrived: "arrived",
} as const;

interface Props {
  start: string;
  departure: string;
  hour: number;
  onHour: (hour: number) => void;
  playing: boolean;
  onPlaying: (playing: boolean) => void;
  variable: HeatVariable;
  onVariable: (v: HeatVariable) => void;
  showHeat: boolean;
  onShowHeat: (show: boolean) => void;
  heatStatus: "idle" | "loading" | "error" | "ready";
  heatError?: string;
  route: RoutePlan | undefined;
}

export function Timeline(props: Props) {
  const { start, departure, hour, onHour, playing, onPlaying, variable, onVariable, showHeat, onShowHeat } = props;
  const { heatStatus, heatError, route } = props;
  const startMs = new Date(start).getTime();
  const at = new Date(startMs + hour * 3_600_000).toISOString();
  const sinceDeparture = (startMs + hour * 3_600_000 - new Date(departure).getTime()) / 3_600_000;

  // Playback: advance the slider in real time, stop at the end.
  const hourRef = useRef(hour);
  useEffect(() => {
    hourRef.current = hour;
  }, [hour]);
  useEffect(() => {
    if (!playing) return;
    let last = performance.now();
    let frame = requestAnimationFrame(function tick(now) {
      const next = Math.min(HOURS, hourRef.current + ((now - last) / 1000) * PLAY_HOURS_PER_SECOND);
      last = now;
      onHour(next);
      if (next >= HOURS) onPlaying(false);
      else frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [playing, onHour, onPlaying]);

  const hoursFromStart = (iso: string) => (new Date(iso).getTime() - startMs) / 3_600_000;
  const marks = route
    ? [
        ...route.stops.map((s) => ({ h: hoursFromStart(s.start), label: s.kind === "rest" ? "Rest" : "Break" })),
        { h: hoursFromStart(route.arrival), label: "Arrive" },
      ].filter((m) => m.h >= 0 && m.h <= HOURS)
    : [];
  const truck = route ? truckAt(route.positions, hour) : null;

  return (
    <div className="pointer-events-auto rounded-2xl border border-slate-200/80 bg-white/95 p-3 shadow-xl backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              if (!playing && hour >= HOURS) onHour(0);
              onPlaying(!playing);
            }}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-white hover:bg-slate-700"
            aria-label={playing ? "Pause forecast" : "Play forecast"}
          >
            {playing ? (
              <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="currentColor">
                <rect x="3" y="2" width="3.5" height="12" rx="1" />
                <rect x="9.5" y="2" width="3.5" height="12" rx="1" />
              </svg>
            ) : (
              <svg viewBox="0 0 16 16" className="ml-0.5 h-3.5 w-3.5" fill="currentColor">
                <path d="M4 2.5v11a1 1 0 0 0 1.5.86l9-5.5a1 1 0 0 0 0-1.72l-9-5.5A1 1 0 0 0 4 2.5Z" />
              </svg>
            )}
          </button>
          <div className="leading-tight">
            <div className="text-sm font-semibold tabular-nums text-slate-900">{formatDayTime(at)}</div>
            <div className="text-[11px] tabular-nums text-slate-500">
              {sinceDeparture < 0 ? "before departure" : `departure + ${sinceDeparture.toFixed(sinceDeparture % 1 ? 1 : 0)} h`}
              {truck && route && ` · truck ${route.id} ${STATUS_TEXT[truck.status]}`}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <div className="flex rounded-lg bg-slate-100 p-0.5" role="radiogroup" aria-label="Heatmap layer">
            {VARIABLES.map((v) => (
              <button
                key={v}
                type="button"
                role="radio"
                aria-checked={variable === v}
                onClick={() => onVariable(v)}
                className={`rounded-md px-2 py-1 text-xs font-medium ${
                  variable === v ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"
                }`}
              >
                {HEAT_LABEL[v]}
              </button>
            ))}
          </div>
          <label className="flex items-center gap-1 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={showHeat}
              onChange={(e) => onShowHeat(e.target.checked)}
              className="h-3.5 w-3.5 accent-slate-900"
            />
            Heatmap
          </label>
        </div>
      </div>

      <div className="relative mt-2">
        <input
          type="range"
          min={0}
          max={HOURS}
          step={0.25}
          value={hour}
          onChange={(e) => {
            onPlaying(false);
            onHour(Number(e.target.value));
          }}
          className="timeline-range w-full"
          aria-label="Forecast hour"
          aria-valuetext={`${formatDayTime(at)}, ${hour} hours into the forecast window`}
        />
        <div className="pointer-events-none relative h-3 text-[9px] text-slate-400">
          {[0, 12, 24, 36, 48].map((h) => (
            <span
              key={h}
              className="absolute -translate-x-1/2 tabular-nums first:translate-x-0 last:-translate-x-full"
              style={{ left: `${(h / HOURS) * 100}%` }}
            >
              {h === 0 ? "0 h" : `+${h} h`}
            </span>
          ))}
          {marks.map((m, i) => (
            <span
              key={i}
              title={m.label}
              className={`absolute -top-[17px] h-2 w-0.5 -translate-x-1/2 rounded ${m.label === "Arrive" ? "bg-emerald-600" : "bg-blue-900"}`}
              style={{ left: `${(m.h / HOURS) * 100}%` }}
            />
          ))}
        </div>
      </div>

      <div className="mt-1.5 flex items-center gap-3">
        <div className="min-w-0 flex-1">
          {heatStatus === "ready" && <HeatLegend variable={variable} />}
          {heatStatus === "loading" && (
            <div className="flex items-center gap-2 text-xs text-slate-500">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-slate-600" />
              Loading the 48-hour corridor forecast…
            </div>
          )}
          {heatStatus === "error" && <div className="text-xs text-red-600">Heatmap unavailable: {heatError}</div>}
        </div>
      </div>
    </div>
  );
}
