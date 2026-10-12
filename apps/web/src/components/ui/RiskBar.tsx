import type { RiskKey } from "@/lib/api/types";
import { RISK_COLOR, RISK_LABEL, RISK_ORDER } from "@/lib/risk";

/** Share of the route's miles at each risk level. */
export function RiskBar({ miles }: { miles: Record<RiskKey, number> }) {
  const total = RISK_ORDER.reduce((sum, k) => sum + miles[k], 0) || 1;
  const label = RISK_ORDER.filter((k) => miles[k] > 0)
    .map((k) => `${RISK_LABEL[k]} ${Math.round(miles[k])} mi`)
    .join(", ");
  return (
    <div className="flex h-2 w-full overflow-hidden rounded-full bg-slate-200" role="img" aria-label={label}>
      {RISK_ORDER.map((k) =>
        miles[k] > 0 ? (
          <div key={k} style={{ width: `${(miles[k] / total) * 100}%`, background: RISK_COLOR[k] }} />
        ) : null,
      )}
    </div>
  );
}
