import type { RiskKey } from "@/lib/api/types";
import { RISK_COLOR, RISK_LABEL, RISK_TEXT_ON } from "@/lib/risk";

export function RiskChip({ level, size = "sm" }: Readonly<{ level: RiskKey; size?: "xs" | "sm" }>) {
  return (
    <span
      className={`inline-flex items-center rounded-full font-semibold whitespace-nowrap ${
        size === "xs" ? "px-1.5 py-px text-[10px]" : "px-2 py-0.5 text-xs"
      }`}
      style={{ background: RISK_COLOR[level], color: RISK_TEXT_ON[level] }}
    >
      {RISK_LABEL[level]}
    </span>
  );
}
