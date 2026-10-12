import { useEffect, useId, useState } from "react";
import { api } from "../api/client";
import type { Place } from "../api/types";

const COORDS = /^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$/;

/** "39.74, -104.99" is accepted as a place without a search. */
function parseCoordinates(text: string): Place | null {
  const m = COORDS.exec(text);
  if (!m) return null;
  const lat = Number(m[1]);
  const lon = Number(m[2]);
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { label: `${lat.toFixed(4)}, ${lon.toFixed(4)}`, lat, lon };
}

interface Props {
  label: string;
  value: Place | null;
  onChange: (place: Place | null) => void;
  placeholder?: string;
  invalid?: boolean;
}

export function PlaceInput({ label, value, onChange, placeholder, invalid }: Props) {
  const id = useId();
  const [text, setText] = useState(value?.label ?? "");
  const [picked, setPicked] = useState(value?.label ?? "");
  const [found, setFound] = useState<{ query: string; places: Place[] }>({ query: "", places: [] });
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Follow outside changes (swap button, example trips) without fighting the user's typing.
  const [prevValue, setPrevValue] = useState(value);
  if (value !== prevValue) {
    setPrevValue(value);
    if (value) {
      setText(value.label);
      setPicked(value.label);
    }
  }

  const query = text.trim();
  const searchable = query.length >= 3 && query !== picked && !parseCoordinates(query);
  const results = searchable && found.query === query ? found.places : [];

  useEffect(() => {
    if (!searchable) return;
    const controller = new AbortController();
    const timer = window.setTimeout(async () => {
      setLoading(true);
      try {
        const places = await api.geocode(query, controller.signal);
        setFound({ query, places });
        setActive(0);
        setError(null);
        setOpen(true);
      } catch (e) {
        if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "Search failed.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }, 250);
    return () => {
      controller.abort();
      window.clearTimeout(timer);
    };
  }, [query, searchable]);

  const pick = (place: Place) => {
    setPicked(place.label);
    setText(place.label);
    setOpen(false);
    onChange(place);
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "ArrowDown" && results.length) {
      e.preventDefault();
      setOpen(true);
      setActive((i) => (i + 1) % results.length);
    } else if (e.key === "ArrowUp" && results.length) {
      e.preventDefault();
      setActive((i) => (i - 1 + results.length) % results.length);
    } else if (e.key === "Enter") {
      const coords = parseCoordinates(text);
      if (coords) {
        e.preventDefault();
        pick(coords);
      } else if (open && results[active]) {
        e.preventDefault();
        pick(results[active]);
      }
    } else if (e.key === "Escape") {
      setOpen(false);
    }
  };

  const listId = `${id}-list`;
  const showList = open && results.length > 0;
  const noMatches = open && searchable && !loading && found.query === query && results.length === 0;
  return (
    <div className="relative">
      <label htmlFor={id} className="mb-1 block text-xs font-medium text-slate-600">
        {label}
      </label>
      <input
        id={id}
        role="combobox"
        aria-expanded={showList}
        aria-controls={listId}
        aria-autocomplete="list"
        aria-activedescendant={showList ? `${listId}-${active}` : undefined}
        aria-invalid={invalid || undefined}
        autoComplete="off"
        spellCheck={false}
        value={text}
        placeholder={placeholder}
        onChange={(e) => {
          setText(e.target.value);
          setOpen(true);
          if (value) onChange(null);
        }}
        onKeyDown={onKeyDown}
        onFocus={() => setOpen(true)}
        onBlur={() => {
          setOpen(false);
          const coords = parseCoordinates(text);
          if (coords && !value) pick(coords);
        }}
        className={`w-full rounded-lg border bg-white px-3 py-2 pr-8 text-sm text-slate-900 shadow-sm outline-none transition placeholder:text-slate-400 focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10 ${
          invalid ? "border-red-400" : "border-slate-300"
        }`}
      />
      {loading && (
        <span
          aria-hidden
          className="pointer-events-none absolute right-3 top-[34px] h-3 w-3 animate-spin rounded-full border-2 border-slate-300 border-t-slate-700"
        />
      )}
      {showList && (
        <ul
          id={listId}
          role="listbox"
          className="absolute z-30 mt-1 max-h-64 w-full overflow-auto rounded-lg border border-slate-200 bg-white py-1 text-sm shadow-lg"
        >
          {results.map((place, i) => (
            <li
              key={`${place.label}-${i}`}
              id={`${listId}-${i}`}
              role="option"
              aria-selected={i === active}
              onMouseDown={(e) => {
                e.preventDefault();
                pick(place);
              }}
              onMouseEnter={() => setActive(i)}
              className={`cursor-pointer px-3 py-2 ${i === active ? "bg-slate-100" : ""}`}
            >
              {place.label}
            </li>
          ))}
        </ul>
      )}
      {noMatches && <p className="mt-1 text-xs text-slate-500">No matches. Try a city and state, or “lat, lon”.</p>}
      {error && <p className="mt-1 text-xs text-red-600">{error}</p>}
    </div>
  );
}
