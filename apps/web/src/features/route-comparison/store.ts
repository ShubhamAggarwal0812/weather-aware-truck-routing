import { create } from "zustand";

export interface CheckpointRef {
  routeId: string;
  index: number;
}

interface RouteSelection {
  selectedId: string | null;
  hoveredId: string | null;
  /** The checkpoint pinned from the list or a map click. */
  focus: CheckpointRef | null;
  select: (id: string) => void;
  hover: (id: string | null) => void;
  focusCheckpoint: (ref: CheckpointRef | null) => void;
  reset: (selectedId: string | null) => void;
}

export const useRouteSelection = create<RouteSelection>()((set) => ({
  selectedId: null,
  hoveredId: null,
  focus: null,
  select: (id) => set({ selectedId: id, focus: null }),
  hover: (id) => set({ hoveredId: id }),
  focusCheckpoint: (ref) => set({ focus: ref }),
  reset: (selectedId) => set({ selectedId, hoveredId: null, focus: null }),
}));
