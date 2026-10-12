import { keepPreviousData, useMutation, useQuery } from "@tanstack/react-query";
import { useDebouncedValue } from "@/hooks/useDebouncedValue";
import { api } from "@/lib/api/client";

export function usePlanTrip() {
  return useMutation({ mutationKey: ["plan"], mutationFn: api.planTrip });
}

/** Debounced, cached place search. Results stay visible while the next query loads. */
export function usePlaceSearch(query: string, enabled: boolean) {
  const debounced = useDebouncedValue(query, 250);
  const ready = enabled && debounced.length >= 3 && debounced === query;
  return useQuery({
    queryKey: ["places", debounced.toLowerCase()],
    queryFn: ({ signal }) => api.searchPlaces(debounced, signal),
    enabled: ready,
    staleTime: 10 * 60_000,
    placeholderData: keepPreviousData,
  });
}
