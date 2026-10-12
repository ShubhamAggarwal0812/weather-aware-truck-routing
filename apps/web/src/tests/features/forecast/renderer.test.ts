import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { HeatmapRenderer } from "@/features/forecast/heatmap/renderer";
import type { Corridor } from "@/lib/api/types";
import { RISK_COLOR } from "@/lib/risk";
import { RULES } from "../../fixtures/plan";

class TestImageData {
  readonly data: Uint8ClampedArray;

  constructor(
    readonly width: number,
    readonly height: number,
  ) {
    this.data = new Uint8ClampedArray(width * height * 4);
  }
}

beforeEach(() => {
  vi.stubGlobal("ImageData", TestImageData);
  vi.spyOn(HTMLCanvasElement.prototype, "getContext").mockReturnValue(null);
});
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function corridor(riskByHour: number[][]): Corridor {
  const calm = riskByHour.map((levels) => levels.map(() => 0));
  return {
    step_deg: 1,
    rows: [40, 40],
    cols: [-100, -99],
    times: Array.from(riskByHour.keys(), (hour) => new Date(Date.UTC(2026, 9, 13, 12 + hour)).toISOString()),
    wind_mph: calm,
    rain_in_hr: calm,
    snow_in_hr: calm,
    risk: riskByHour,
  };
}

const hex = (channels: number[]) => `#${channels.map((channel) => channel.toString(16).padStart(2, "0")).join("")}`;

function coloursDrawn(image: ImageData): Set<string> {
  const colours = new Set<string>();
  for (let pixel = 0; pixel < image.width * image.height; pixel++) {
    const [red, green, blue, alpha] = image.data.slice(pixel * 4, pixel * 4 + 4);
    if (alpha > 0) colours.add(hex([red, green, blue]));
  }
  return colours;
}

describe("HeatmapRenderer", () => {
  it("should draw risk for the hour the time falls in, without blending hours", () => {
    const renderer = new HeatmapRenderer(
      corridor([
        [0, 0],
        [4, 4],
      ]),
      [],
      RULES,
    );
    expect(coloursDrawn(renderer.draw("risk", 0.5))).toEqual(new Set([RISK_COLOR.low]));
    expect(coloursDrawn(renderer.draw("risk", 1))).toEqual(new Set([RISK_COLOR.no_travel]));
  });

  it("should draw every risk pixel in a level the forecast has, without blending cells", () => {
    const renderer = new HeatmapRenderer(corridor([[0, 4]]), [], RULES);
    expect(coloursDrawn(renderer.draw("risk", 0))).toEqual(new Set([RISK_COLOR.low, RISK_COLOR.no_travel]));
  });
});
