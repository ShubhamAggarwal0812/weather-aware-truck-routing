import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CheckpointList } from "@/features/route-comparison";
import { checkpoint, route } from "../../fixtures/plan";

describe("CheckpointList", () => {
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
