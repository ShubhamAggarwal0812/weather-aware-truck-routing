import { describe, expect, it } from "vitest";
import { truckAt } from "@/features/forecast/truck";

const positions = [
  [40, -105, 0], // waiting
  [40, -104, 1], // driving
  [41, -103, 3], // resting
];

describe("truckAt", () => {
  it("interpolates between the 15-minute samples", () => {
    const at = truckAt(positions, 0.125); // halfway between samples 0 and 1
    expect(at.lat).toBeCloseTo(40);
    expect(at.lon).toBeCloseTo(-104.5);
    expect(at.status).toBe("waiting");
  });

  it("clamps to the window", () => {
    expect(truckAt(positions, 10)).toEqual({ lat: 41, lon: -103, status: "rest" });
    expect(truckAt(positions, -1).status).toBe("waiting");
  });
});
