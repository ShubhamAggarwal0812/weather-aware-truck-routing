interface Option<T extends string | number> {
  value: T;
  label: string;
}

const STEP_BY_KEY: Readonly<Partial<Record<string, number>>> = {
  ArrowRight: 1,
  ArrowDown: 1,
  ArrowLeft: -1,
  ArrowUp: -1,
};

interface Props<T extends string | number> {
  label: string;
  options: Option<T>[];
  value: T;
  onChange: (value: T) => void;
  size?: "sm" | "md";
}

/** A radio group styled as a segmented control; arrow keys move between options. */
export function SegmentedControl<T extends string | number>({
  label,
  options,
  value,
  onChange,
  size = "md",
}: Readonly<Props<T>>) {
  const pad = size === "sm" ? "px-2 py-1 text-xs" : "py-1.5 text-sm";
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className={`grid gap-1 rounded-lg bg-slate-100 p-0.5`}
      style={{ gridTemplateColumns: `repeat(${options.length}, minmax(0, 1fr))` }}
    >
      {options.map((option) => {
        const checked = option.value === value;
        return (
          <button
            key={option.value}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            onClick={() => onChange(option.value)}
            onKeyDown={(e) => {
              const i = options.findIndex((o) => o.value === value);
              const step = STEP_BY_KEY[e.key] ?? 0;
              if (!step) return;
              e.preventDefault();
              const next = options[(i + step + options.length) % options.length];
              onChange(next.value);
              (e.currentTarget.parentElement?.children[options.indexOf(next)] as HTMLElement | undefined)?.focus();
            }}
            className={`rounded-md text-center font-medium transition focus-visible:ring-2 focus-visible:ring-slate-900/30 focus-visible:outline-none ${pad} ${
              checked ? "bg-white text-slate-900 shadow-sm" : "text-slate-500 hover:text-slate-800"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
