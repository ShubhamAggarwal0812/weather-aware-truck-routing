import { useState } from "react";
import type { Place, PlanRequest } from "../api/types";
import { nextQuarterHour, timeZoneName, toLocalInputValue } from "../lib/format";
import { PlaceInput } from "./PlaceInput";

const INTERVALS = [10, 25, 50] as const;
const MAX_LOAD_LB = 80_000;
const MAX_DAYS_AHEAD = 7;

export const EXAMPLES: { name: string; origin: Place; destination: Place; load: number }[] = [
  {
    name: "Denver → Chicago",
    origin: { label: "Denver, Colorado", lat: 39.7392, lon: -104.9903 },
    destination: { label: "Chicago, Illinois", lat: 41.8781, lon: -87.6298 },
    load: 42_000,
  },
  {
    name: "Salt Lake City → Kansas City",
    origin: { label: "Salt Lake City, Utah", lat: 40.7608, lon: -111.891 },
    destination: { label: "Kansas City, Missouri", lat: 39.0997, lon: -94.5786 },
    load: 32_000,
  },
  {
    name: "Dallas → Atlanta",
    origin: { label: "Dallas, Texas", lat: 32.7767, lon: -96.797 },
    destination: { label: "Atlanta, Georgia", lat: 33.749, lon: -84.388 },
    load: 25_000,
  },
];

interface Props {
  loading: boolean;
  onSubmit: (request: PlanRequest) => void;
}

export function TripForm({ loading, onSubmit }: Props) {
  const [origin, setOrigin] = useState<Place | null>(null);
  const [destination, setDestination] = useState<Place | null>(null);
  const [departure, setDeparture] = useState(() => toLocalInputValue(nextQuarterHour()));
  const [load, setLoad] = useState("42000");
  const [interval, setIntervalMiles] = useState<(typeof INTERVALS)[number]>(25);
  const [restBreaks, setRestBreaks] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);

  const now = new Date();
  const maxDeparture = new Date(now.getTime() + MAX_DAYS_AHEAD * 86_400_000);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const problems: string[] = [];
    if (!origin) problems.push("Pick an origin from the suggestions.");
    if (!destination) problems.push("Pick a destination from the suggestions.");
    const departAt = new Date(departure);
    if (Number.isNaN(departAt.getTime())) problems.push("Enter a departure date and time.");
    else if (departAt.getTime() < now.getTime() - 30 * 60_000) problems.push("Departure can't be in the past.");
    else if (departAt > maxDeparture) problems.push(`Departure must be within ${MAX_DAYS_AHEAD} days.`);
    const loadLb = Number(load);
    if (!Number.isFinite(loadLb) || loadLb < 0 || loadLb > MAX_LOAD_LB)
      problems.push(`Load weight must be between 0 and ${MAX_LOAD_LB.toLocaleString()} lb.`);
    setErrors(problems);
    if (problems.length || !origin || !destination) return;
    onSubmit({
      origin,
      destination,
      departure: departAt.toISOString(),
      load_weight_lb: Math.round(loadLb),
      interval_miles: interval,
      rest_breaks: restBreaks,
    });
  };

  const applyExample = (ex: (typeof EXAMPLES)[number]) => {
    setOrigin(ex.origin);
    setDestination(ex.destination);
    setLoad(String(ex.load));
    setErrors([]);
  };

  return (
    <form onSubmit={submit} className="space-y-3" noValidate>
      <div className="relative space-y-2">
        <PlaceInput
          label="Origin"
          value={origin}
          onChange={setOrigin}
          placeholder="City, address or “lat, lon”"
          invalid={errors.length > 0 && !origin}
        />
        <PlaceInput
          label="Destination"
          value={destination}
          onChange={setDestination}
          placeholder="City, address or “lat, lon”"
          invalid={errors.length > 0 && !destination}
        />
        <button
          type="button"
          onClick={() => {
            setOrigin(destination);
            setDestination(origin);
          }}
          className="absolute right-0 top-[58px] z-10 rounded-full border border-slate-300 bg-white p-1 text-slate-500 shadow-sm hover:text-slate-900"
          aria-label="Swap origin and destination"
          title="Swap"
        >
          <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8">
            <path d="M7 4v12M7 16l-3-3M7 16l3-3M13 16V4M13 4l-3 3M13 4l3 3" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      <div className="grid grid-cols-2 gap-2">
        <div>
          <label htmlFor="departure" className="mb-1 block text-xs font-medium text-slate-600">
            Departure <span className="font-normal text-slate-400">({timeZoneName()})</span>
          </label>
          <input
            id="departure"
            type="datetime-local"
            value={departure}
            min={toLocalInputValue(now)}
            max={toLocalInputValue(maxDeparture)}
            onChange={(e) => setDeparture(e.target.value)}
            className="w-full rounded-lg border border-slate-300 bg-white px-2 py-2 text-sm text-slate-900 shadow-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10"
          />
        </div>
        <div>
          <label htmlFor="load" className="mb-1 block text-xs font-medium text-slate-600">
            Load weight
          </label>
          <div className="relative">
            <input
              id="load"
              type="number"
              inputMode="numeric"
              min={0}
              max={MAX_LOAD_LB}
              step={1000}
              value={load}
              onChange={(e) => setLoad(e.target.value)}
              className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-3 pr-8 text-sm text-slate-900 shadow-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10"
            />
            <span className="pointer-events-none absolute right-3 top-2 text-sm text-slate-400">lb</span>
          </div>
        </div>
      </div>
      <p className="text-[11px] leading-snug text-slate-500">
        Cargo only. Over 30,000 lb, 45–54 mph wind is No Travel. Over 40,000 lb, 35–44 mph wind is Severe.
      </p>

      <fieldset>
        <legend className="mb-1 text-xs font-medium text-slate-600">Weather checkpoint every</legend>
        <div className="grid grid-cols-3 gap-1 rounded-lg bg-slate-100 p-1">
          {INTERVALS.map((mi) => (
            <label
              key={mi}
              className={`cursor-pointer rounded-md py-1.5 text-center text-sm font-medium transition has-focus-visible:ring-2 has-focus-visible:ring-slate-900/30 ${
                interval === mi ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"
              }`}
            >
              <input
                type="radio"
                name="interval"
                value={mi}
                checked={interval === mi}
                onChange={() => setIntervalMiles(mi)}
                className="sr-only"
              />
              {mi} mi
            </label>
          ))}
        </div>
      </fieldset>

      <label className="flex items-start gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={restBreaks}
          onChange={(e) => setRestBreaks(e.target.checked)}
          className="mt-0.5 h-4 w-4 accent-slate-900"
        />
        <span>
          Include HOS breaks in ETAs
          <span className="block text-[11px] text-slate-500">30 min after 8 h driving, 10 h rest after 11 h.</span>
        </span>
      </label>

      {errors.length > 0 && (
        <ul className="rounded-lg bg-red-50 px-3 py-2 text-sm text-red-700" role="alert">
          {errors.map((e) => (
            <li key={e}>{e}</li>
          ))}
        </ul>
      )}

      <button
        type="submit"
        disabled={loading}
        className="flex w-full items-center justify-center gap-2 rounded-lg bg-slate-900 px-4 py-2.5 text-sm font-semibold text-white shadow-sm transition hover:bg-slate-800 disabled:cursor-wait disabled:opacity-70"
      >
        {loading && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />}
        {loading ? "Checking routes and weather…" : "Find the safest route"}
      </button>

      <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
        <span>Try:</span>
        {EXAMPLES.map((ex) => (
          <button
            key={ex.name}
            type="button"
            onClick={() => applyExample(ex)}
            className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-slate-600 hover:border-slate-400 hover:text-slate-900"
          >
            {ex.name}
          </button>
        ))}
      </div>
    </form>
  );
}
