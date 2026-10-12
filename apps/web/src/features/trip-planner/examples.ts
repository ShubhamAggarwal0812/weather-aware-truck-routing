import type { Location } from "@/lib/api/types";

export interface ExampleTrip {
  name: string;
  origin: Location;
  destination: Location;
  loadLb: number;
}

export const EXAMPLES: ExampleTrip[] = [
  {
    name: "Denver → Chicago",
    origin: { label: "Denver, CO", lat: 39.7392, lon: -104.9903 },
    destination: { label: "Chicago, IL", lat: 41.8781, lon: -87.6298 },
    loadLb: 42_000,
  },
  {
    name: "Salt Lake City → Kansas City",
    origin: { label: "Salt Lake City, UT", lat: 40.7608, lon: -111.891 },
    destination: { label: "Kansas City, MO", lat: 39.0997, lon: -94.5786 },
    loadLb: 32_000,
  },
  {
    name: "Dallas → Atlanta",
    origin: { label: "Dallas, TX", lat: 32.7767, lon: -96.797 },
    destination: { label: "Atlanta, GA", lat: 33.749, lon: -84.388 },
    loadLb: 25_000,
  },
];
