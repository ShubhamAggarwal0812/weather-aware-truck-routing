/** Truck position codes from the API's `positions`: [lat, lon, status]. */
export const TRUCK_STATUS = ["waiting", "driving", "break", "rest", "arrived"] as const;
export type TruckStatus = (typeof TRUCK_STATUS)[number];

/** Truck position at a fractional hour, from the backend's 15-minute samples. */
export function truckAt(positions: number[][], hour: number): { lat: number; lon: number; status: TruckStatus } {
  const x = Math.min(Math.max(hour * 4, 0), positions.length - 1);
  const i = Math.floor(x);
  const j = Math.min(i + 1, positions.length - 1);
  const f = x - i;
  const [lat0, lon0, s0] = positions[i];
  const [lat1, lon1] = positions[j];
  return { lat: lat0 + (lat1 - lat0) * f, lon: lon0 + (lon1 - lon0) * f, status: TRUCK_STATUS[s0] };
}
