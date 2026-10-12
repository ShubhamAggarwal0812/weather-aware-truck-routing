import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it } from "vitest";
import { Recommendation, RouteCards, useRouteSelection } from "@/features/route-comparison";
import { plan } from "../../fixtures/plan";

describe("RouteCards", () => {
  beforeEach(() => useRouteSelection.getState().reset("B"));

  it("marks the recommended route and shows risk miles", () => {
    render(<RouteCards plan={plan()} />);
    const cards = screen.getAllByRole("radio");
    expect(cards).toHaveLength(2);
    expect(within(cards[1]).getByText("Recommended")).toBeInTheDocument();
    expect(cards[1]).toHaveAttribute("aria-checked", "true");
    expect(within(cards[0]).getByText("Severe 36 mi")).toBeInTheDocument();
  });

  it("selects a route on click", async () => {
    render(<RouteCards plan={plan()} />);
    await userEvent.click(screen.getAllByRole("radio")[0]);
    expect(useRouteSelection.getState().selectedId).toBe("A");
  });

  it("explains when fewer than three routes exist", () => {
    render(<RouteCards plan={plan()} />);
    expect(screen.getByText("Only 2 distinct routes exist for this trip.")).toBeInTheDocument();
  });
});

describe("Recommendation", () => {
  it("shows the headline and reasons", () => {
    render(<Recommendation plan={plan()} />);
    expect(screen.getByText("Route B is the safest option.")).toBeInTheDocument();
    expect(screen.getByText(/Fewer Severe miles than Route A/)).toBeInTheDocument();
  });
});
