import type { Plan } from "../api/types";

export function Recommendation({ plan }: { plan: Plan }) {
  const { recommendation: rec } = plan;
  return (
    <section
      className={`rounded-xl border p-3 ${rec.safe ? "border-emerald-200 bg-emerald-50" : "border-purple-200 bg-purple-50"}`}
      aria-live="polite"
    >
      <div className={`text-sm font-semibold ${rec.safe ? "text-emerald-900" : "text-purple-900"}`}>{rec.headline}</div>
      {rec.reasons.length > 0 && (
        <ul className={`mt-1.5 space-y-0.5 text-xs ${rec.safe ? "text-emerald-800" : "text-purple-800"}`}>
          {rec.reasons.map((r) => (
            <li key={r} className="flex gap-1.5">
              <span aria-hidden>•</span>
              {r}
            </li>
          ))}
        </ul>
      )}
      <p className="mt-2 text-[11px] text-slate-500">
        Ranked by fewest No Travel miles, then Severe miles, High miles, average risk, and travel time.
      </p>
    </section>
  );
}
