import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Spinner } from "@/components/ui/Spinner";
import { useRouteSelection } from "@/features/route-comparison";
import type { HeatVariable, Plan } from "@/lib/api/types";
import { formatDayTime } from "@/lib/format";
import { useCorridorForecast } from "../api";
import { HEAT_LABEL } from "../heatmap/colors";
import { usePlayback } from "../hooks/usePlayback";
import { FORECAST_HOURS, useForecastView } from "../store";
import { truckAt } from "../truck";
import { HeatLegend } from "./HeatLegend";

const LAYERS: { value: HeatVariable; label: string }[] = (
  ["risk", "wind_mph", "rain_in_hr", "snow_in_hr"] as const
).map((v) => ({ value: v, label: HEAT_LABEL[v] }));
const STATUS_TEXT = {
  waiting: "not departed",
  driving: "driving",
  break: "on a 30-min break",
  rest: "on a 10-h rest",
  arrived: "arrived",
} as const;
const HOUR_MS = 3_600_000;
const MARK_TITLE = { arrive: "Arrival", rest: "10-hour rest", break: "30-minute break" } as const;

function tickAlignment(hour: number): string {
  if (hour === 0) return "";
  return hour === FORECAST_HOURS ? "-translate-x-full" : "-translate-x-1/2";
}

/** Forecast slider, playback, heatmap layer picker and legend. */
export function Timeline({ plan }: Readonly<{ plan: Plan }>) {
  usePlayback();
  const { hour, playing, variable, showHeat, setHour, setPlaying, setVariable, setShowHeat } = useForecastView();
  const selectedId = useRouteSelection((s) => s.selectedId);
  const corridor = useCorridorForecast(plan);
  const route = plan.routes.find((r) => r.id === selectedId);

  const startMs = new Date(plan.heatmap_start).getTime();
  const at = new Date(startMs + hour * HOUR_MS).toISOString();
  const sinceDeparture = (startMs + hour * HOUR_MS - new Date(plan.departure).getTime()) / HOUR_MS;
  const hoursFromStart = (iso: string) => (new Date(iso).getTime() - startMs) / HOUR_MS;
  const marks = route
    ? [
        ...route.stops.map((s) => ({ h: hoursFromStart(s.start), kind: s.kind })),
        { h: hoursFromStart(route.arrival), kind: "arrive" as const },
      ].filter((m) => m.h >= 0 && m.h <= FORECAST_HOURS)
    : [];
  const truck = route ? truckAt(route.positions, hour) : null;

  return (
    <div className="pointer-events-auto md:rounded-2xl md:border md:border-slate-200/80 md:bg-white/95 md:p-3 md:shadow-xl md:backdrop-blur">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => {
              if (!playing && hour >= FORECAST_HOURS) setHour(0);
              setPlaying(!playing);
            }}
            className="flex h-8 w-8 items-center justify-center rounded-full bg-slate-900 text-white hover:bg-slate-700"
            aria-label={playing ? "Pause forecast" : "Play forecast"}
          >
            {playing ? (
              <svg viewBox="0 0 16 16" className="h-3.5 w-3.5" fill="currentColor" aria-hidden>
                <rect x="3" y="2" width="3.5" height="12" rx="1" />
                <rect x="9.5" y="2" width="3.5" height="12" rx="1" />
              </svg>
            ) : (
              <svg viewBox="0 0 16 16" className="ml-0.5 h-3.5 w-3.5" fill="currentColor" aria-hidden>
                <path d="M4 2.5v11a1 1 0 0 0 1.5.86l9-5.5a1 1 0 0 0 0-1.72l-9-5.5A1 1 0 0 0 4 2.5Z" />
              </svg>
            )}
          </button>
          <div className="leading-tight">
            <div className="text-sm font-semibold text-slate-900 tabular-nums">{formatDayTime(at)}</div>
            <div className="text-[11px] text-slate-500 tabular-nums">
              {sinceDeparture < 0 ? "before departure" : `departure + ${+sinceDeparture.toFixed(1)} h`}
              {truck && route && ` · truck ${route.id} ${STATUS_TEXT[truck.status]}`}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <SegmentedControl label="Heatmap layer" options={LAYERS} value={variable} onChange={setVariable} size="sm" />
          <label className="flex items-center gap-1 text-xs text-slate-600">
            <input
              type="checkbox"
              checked={showHeat}
              onChange={(e) => setShowHeat(e.target.checked)}
              className="h-3.5 w-3.5 accent-slate-900"
            />
            <span>Heatmap</span>
          </label>
        </div>
      </div>

      <div className="relative mt-2">
        <input
          type="range"
          min={0}
          max={FORECAST_HOURS}
          step={0.25}
          value={hour}
          onChange={(e) => {
            setPlaying(false);
            setHour(Number(e.target.value));
          }}
          className="timeline-range w-full"
          aria-label="Forecast hour"
          aria-valuetext={`${formatDayTime(at)}, ${hour} hours into the forecast window`}
        />
        <div className="pointer-events-none relative h-3 text-[9px] text-slate-400">
          {[0, 12, 24, 36, 48].map((h) => (
            <span
              key={h}
              // Edge labels align inwards so they never stick out of the panel.
              className={`absolute whitespace-nowrap tabular-nums ${tickAlignment(h)}`}
              style={{ left: `${(h / FORECAST_HOURS) * 100}%` }}
            >
              {h === 0 ? "0 h" : `+${h} h`}
            </span>
          ))}
          {marks.map((mark) => (
            <span
              key={`${mark.kind}-${mark.h}`}
              title={MARK_TITLE[mark.kind]}
              className={`absolute -top-[17px] h-2 w-0.5 -translate-x-1/2 rounded ${mark.kind === "arrive" ? "bg-emerald-600" : "bg-blue-900"}`}
              style={{ left: `${(mark.h / FORECAST_HOURS) * 100}%` }}
            />
          ))}
        </div>
      </div>

      <div className="mt-1.5 min-h-[26px]">
        {corridor.isSuccess && <HeatLegend variable={variable} rules={plan.rules} />}
        {corridor.isPending && (
          <div className="flex items-center gap-2 text-xs text-slate-500">
            <Spinner className="h-3 w-3" />
            Loading the 48-hour corridor forecast…
          </div>
        )}
        {corridor.isError && (
          <div className="flex items-center gap-2 text-xs text-red-600" role="alert">
            Heatmap unavailable: {corridor.error.message}
            <button
              type="button"
              onClick={() => corridor.refetch()}
              className="rounded border border-red-200 px-1.5 py-0.5 font-medium hover:bg-red-50"
            >
              Retry
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
