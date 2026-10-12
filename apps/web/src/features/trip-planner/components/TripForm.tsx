import { useState } from "react";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { Spinner } from "@/components/ui/Spinner";
import type { Location, PlanRequest } from "@/lib/api/types";
import { formatRanges, nextQuarterHour, timeZoneName, toLocalInputValue } from "@/lib/format";
import { RISK_LABEL } from "@/lib/risk";
import { useAppConfig } from "../api";
import { EXAMPLES, type ExampleTrip } from "../examples";
import { PlaceInput } from "./PlaceInput";

type IntervalMiles = NonNullable<PlanRequest["interval_miles"]>;

const INTERVALS: { value: IntervalMiles; label: string }[] = [
  { value: 10, label: "10 mi" },
  { value: 25, label: "25 mi" },
  { value: 50, label: "50 mi" },
];
const MAX_LOAD_LB = 80_000;
const MAX_DAYS_AHEAD = 7;
const GRACE_MS = 30 * 60_000;

interface FormValues {
  origin: Location | null;
  destination: Location | null;
  departure: string; // datetime-local value, browser time zone
  load: string;
}

/** Client-side checks that mirror the API's, so most mistakes never cost a round trip. */
export function validateTrip(values: FormValues, now = new Date()): string[] {
  const problems: string[] = [];
  if (!values.origin) problems.push("Pick an origin from the suggestions.");
  if (!values.destination) problems.push("Pick a destination from the suggestions.");
  const departAt = new Date(values.departure);
  if (Number.isNaN(departAt.getTime())) problems.push("Enter a departure date and time.");
  else if (departAt.getTime() < now.getTime() - GRACE_MS) problems.push("Departure can't be in the past.");
  else if (departAt.getTime() > now.getTime() + MAX_DAYS_AHEAD * 86_400_000)
    problems.push(`Departure must be within ${MAX_DAYS_AHEAD} days.`);
  const load = Number(values.load);
  if (values.load.trim() === "" || !Number.isFinite(load) || load < 0 || load > MAX_LOAD_LB)
    problems.push(`Load weight must be between 0 and ${MAX_LOAD_LB.toLocaleString()} lb.`);
  return problems;
}

interface Props {
  loading: boolean;
  onSubmit: (request: PlanRequest) => void;
}

export function TripForm({ loading, onSubmit }: Readonly<Props>) {
  const [origin, setOrigin] = useState<Location | null>(null);
  const [destination, setDestination] = useState<Location | null>(null);
  const [departure, setDeparture] = useState(() => toLocalInputValue(nextQuarterHour()));
  const [load, setLoad] = useState("42000");
  const [intervalMiles, setIntervalMiles] = useState<IntervalMiles>(25);
  const [restBreaks, setRestBreaks] = useState(true);
  const [errors, setErrors] = useState<string[]>([]);
  const loadRules = useAppConfig().data?.rules.load_rules ?? [];

  const now = new Date();
  const submit = (event: React.SubmitEvent<HTMLFormElement>) => {
    event.preventDefault();
    const problems = validateTrip({ origin, destination, departure, load });
    setErrors(problems);
    if (problems.length || !origin || !destination) return;
    onSubmit({
      origin,
      destination,
      departure: new Date(departure).toISOString(),
      load_weight_lb: Math.round(Number(load)),
      interval_miles: intervalMiles,
      rest_breaks: restBreaks,
    });
  };

  const applyExample = (example: ExampleTrip) => {
    setOrigin(example.origin);
    setDestination(example.destination);
    setLoad(String(example.loadLb));
    setErrors([]);
  };

  const inputClass =
    "w-full rounded-lg border border-slate-300 bg-white py-2 text-sm text-slate-900 shadow-sm outline-none focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10";

  return (
    <form onSubmit={submit} className="space-y-3" noValidate aria-label="Trip details">
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
          className="absolute top-[58px] right-0 z-10 rounded-full border border-slate-300 bg-white p-1 text-slate-500 shadow-sm hover:text-slate-900"
          aria-label="Swap origin and destination"
          title="Swap"
        >
          <svg viewBox="0 0 20 20" className="h-4 w-4" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
            <path
              d="M7 4v12M7 16l-3-3M7 16l3-3M13 16V4M13 4l-3 3M13 4l3 3"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
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
            max={toLocalInputValue(new Date(now.getTime() + MAX_DAYS_AHEAD * 86_400_000))}
            onChange={(e) => setDeparture(e.target.value)}
            className={`${inputClass} px-2`}
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
              className={`${inputClass} pr-8 pl-3`}
            />
            <span className="pointer-events-none absolute top-2 right-3 text-sm text-slate-400">lb</span>
          </div>
        </div>
      </div>
      <p className="text-[11px] leading-snug text-slate-500">
        Cargo only.
        {loadRules.map((rule) => ` ${formatRanges(rule.description)} is ${RISK_LABEL[rule.level]}.`).join("")}
      </p>

      <div>
        <div className="mb-1 text-xs font-medium text-slate-600">Weather checkpoint every</div>
        <SegmentedControl
          label="Weather checkpoint every"
          options={INTERVALS}
          value={intervalMiles}
          onChange={setIntervalMiles}
        />
      </div>

      <label className="flex items-start gap-2 text-sm text-slate-700">
        <input
          type="checkbox"
          checked={restBreaks}
          onChange={(e) => setRestBreaks(e.target.checked)}
          className="mt-0.5 h-4 w-4 accent-slate-900"
        />
        <span>
          Include HOS breaks in ETAs{" "}
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
        {loading && <Spinner tone="light" />}
        {loading ? "Checking routes and weather…" : "Find the safest route"}
      </button>

      <div className="flex flex-wrap items-center gap-1.5 text-xs text-slate-500">
        <span>Try:</span>
        {EXAMPLES.map((example) => (
          <button
            key={example.name}
            type="button"
            onClick={() => applyExample(example)}
            className="rounded-full border border-slate-200 bg-white px-2 py-0.5 text-slate-600 hover:border-slate-400 hover:text-slate-900"
          >
            {example.name}
          </button>
        ))}
      </div>
    </form>
  );
}
