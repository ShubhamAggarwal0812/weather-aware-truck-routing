import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { HeatLegend } from "@/features/forecast/components/HeatLegend";
import { RULES } from "../../fixtures/plan";

describe("HeatLegend", () => {
  it("should label the ticks with the rules' thresholds", () => {
    const rules = {
      ...RULES,
      rain_in_hr: [
        { level: "moderate" as const, threshold: 0.2, inclusive: true },
        { level: "no_travel" as const, threshold: 0.8, inclusive: false },
      ],
    };
    render(<HeatLegend variable="rain_in_hr" rules={rules} />);
    expect(screen.getByText("0.2")).toBeInTheDocument();
    expect(screen.getByText("0.8")).toBeInTheDocument();
    expect(screen.queryByText("0.25")).not.toBeInTheDocument();
  });

  it("should name every risk level", () => {
    render(<HeatLegend variable="risk" rules={RULES} />);
    for (const label of ["Low", "Moderate", "High", "Severe", "No Travel"]) {
      expect(screen.getByText(label)).toBeInTheDocument();
    }
  });

  it("should draw one solid block per risk level", () => {
    const { container } = render(<HeatLegend variable="risk" rules={RULES} />);
    const bar = container.firstElementChild?.firstElementChild as HTMLElement;
    const blocks = [...bar.style.background.matchAll(/(\d+(?:\.\d+)?)% (\d+(?:\.\d+)?)%/g)].map((match) => [
      Number(match[1]),
      Number(match[2]),
    ]);
    expect(blocks).toEqual([
      [0, 20],
      [20, 40],
      [40, 60],
      [60, 80],
      [80, 100],
    ]);
  });
});
