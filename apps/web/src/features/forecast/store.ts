import { create } from "zustand";
import type { HeatVariable } from "@/lib/api/types";

export const FORECAST_HOURS = 48;

interface ForecastView {
  /** Hours since the top of the departure hour, in 15-minute steps (0–48). */
  hour: number;
  playing: boolean;
  variable: HeatVariable;
  showHeat: boolean;
  setHour: (hour: number) => void;
  setPlaying: (playing: boolean) => void;
  setVariable: (variable: HeatVariable) => void;
  setShowHeat: (show: boolean) => void;
  /** Back to departure for a new plan; layer choices are kept. */
  rewind: () => void;
}

export const useForecastView = create<ForecastView>()((set) => ({
  hour: 0,
  playing: false,
  variable: "risk",
  showHeat: true,
  setHour: (hour) => set({ hour: Math.min(Math.max(hour, 0), FORECAST_HOURS) }),
  setPlaying: (playing) => set({ playing }),
  setVariable: (variable) => set({ variable }),
  setShowHeat: (showHeat) => set({ showHeat }),
  rewind: () => set({ hour: 0, playing: false }),
}));
