import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CheckpointList } from "@/features/route-comparison";
import { CheckpointDetails } from "@/features/route-comparison/components/CheckpointDetails";
import { checkpoint, route } from "../../fixtures/plan";

describe("CheckpointList", () => {
  it("should leave a temperature the forecast left out off the row", () => {
    const withTemperature = checkpoint(0);
    const withoutTemperature = { ...checkpoint(1), conditions: { ...checkpoint(1).conditions, temp_f: null } };
    render(
      <CheckpointList route={route("A", { checkpoints: [withTemperature, withoutTemperature] })} intervalMiles={25} />,
    );
    const [knownRow, unknownRow] = screen.getAllByRole("listitem");
    expect(knownRow).toHaveTextContent("41°F");
    expect(unknownRow).not.toHaveTextContent(/°F|null/);
  });

  it("should keep route order when checkpoints share a rounded mile", () => {
    // A destination a few metres past the last mark rounds to the same mile.
    const checkpoints = [0, 25, 50, 50].map((mile, index) => ({ ...checkpoint(index), mile }));
    const stop = {
      kind: "break" as const,
      mile: 25,
      lat: 40,
      lon: -104.5,
      start: "2026-10-13T20:00:00Z",
      end: "2026-10-13T20:30:00Z",
    };
    render(<CheckpointList route={route("A", { checkpoints, stops: [stop] })} intervalMiles={25} />);
    const rows = screen.getAllByRole("listitem").map((item) => item.dataset.checkpoint ?? "stop");
    expect(rows).toEqual(["0", "1", "stop", "2", "3"]);
  });
});

describe("CheckpointDetails", () => {
  it("should show gusts and temperature the forecast left out as missing, not as null", () => {
    const withEveryCondition = checkpoint(0);
    const withoutGustsOrTemperature = {
      ...withEveryCondition,
      conditions: { ...withEveryCondition.conditions, gust_mph: null, temp_f: null },
    };
    render(<CheckpointDetails routeId="A" checkpoint={withoutGustsOrTemperature} />);
    expect(screen.getByText("38.2 mph")).toBeInTheDocument();
    expect(screen.getByText("Not forecast")).toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/null|gusts/);
  });
});
