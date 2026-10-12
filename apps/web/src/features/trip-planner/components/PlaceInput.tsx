import { useId, useState } from "react";
import { Spinner } from "@/components/ui/Spinner";
import type { Location, Place } from "@/lib/api/types";
import { usePlaceSearch } from "../api";

const COORDS = /^\s*(-?\d{1,2}(?:\.\d+)?)\s*,\s*(-?\d{1,3}(?:\.\d+)?)\s*$/;

/** "39.74, -104.99" is accepted as a place without a search. */
export function parseCoordinates(text: string): Place | null {
  const m = COORDS.exec(text);
  if (!m) return null;
  const lat = Number(m[1]);
  const lon = Number(m[2]);
  if (Math.abs(lat) > 90 || Math.abs(lon) > 180) return null;
  return { label: `${lat.toFixed(4)}, ${lon.toFixed(4)}`, lat, lon };
}

interface Props {
  label: string;
  value: Location | null;
  onChange: (place: Location | null) => void;
  placeholder?: string;
  invalid?: boolean;
}

/** Accessible combobox over the place-search API. */
export function PlaceInput({ label, value, onChange, placeholder, invalid }: Readonly<Props>) {
  const id = useId();
  const [text, setText] = useState(value?.label ?? "");
  const [picked, setPicked] = useState(value?.label ?? "");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);

  // Follow outside changes (swap button, example trips) without fighting the user's typing.
  // Typing clears the value too, but then the text no longer matches the picked label.
  const [prevValue, setPrevValue] = useState(value);
  if (value !== prevValue) {
    setPrevValue(value);
    if (value) {
      setText(value.label ?? "");
      setPicked(value.label ?? "");
    } else if (text === picked) {
      setText("");
      setPicked("");
    }
  }

  const query = text.trim();
  const searchable = query !== picked && !parseCoordinates(query);
  const search = usePlaceSearch(query, searchable);
  const results = searchable && query.length >= 3 ? (search.data ?? []) : [];

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
  const noMatches = open && searchable && search.isSuccess && !search.isPlaceholderData && results.length === 0;
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
          setActive(0);
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
        className={`w-full rounded-lg border bg-white px-3 py-2 pr-8 text-sm text-slate-900 shadow-sm transition outline-none placeholder:text-slate-400 focus:border-slate-900 focus:ring-2 focus:ring-slate-900/10 ${
          invalid ? "border-red-400" : "border-slate-300"
        }`}
      />
      {search.isFetching && <Spinner className="pointer-events-none absolute top-[34px] right-3 h-3 w-3" />}
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
      {search.isError && <p className="mt-1 text-xs text-red-600">{search.error.message}</p>}
    </div>
  );
}
