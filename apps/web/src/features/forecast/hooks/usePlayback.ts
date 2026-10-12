import { useEffect } from "react";
import { FORECAST_HOURS, useForecastView } from "../store";

const HOURS_PER_SECOND = 3;

/** While playing, advances the forecast hour in real time and stops at the end. */
export function usePlayback() {
  const playing = useForecastView((s) => s.playing);
  useEffect(() => {
    if (!playing) return;
    const { setHour, setPlaying } = useForecastView.getState();
    let last = performance.now();
    let frame = requestAnimationFrame(function tick(now) {
      const next = Math.min(FORECAST_HOURS, useForecastView.getState().hour + ((now - last) / 1000) * HOURS_PER_SECOND);
      last = now;
      setHour(next);
      if (next >= FORECAST_HOURS) setPlaying(false);
      else frame = requestAnimationFrame(tick);
    });
    return () => cancelAnimationFrame(frame);
  }, [playing]);
}
