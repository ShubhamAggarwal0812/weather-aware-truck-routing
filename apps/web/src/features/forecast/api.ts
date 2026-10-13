import { useQuery } from "@tanstack/react-query";
import { api, isTransient } from "@/lib/api/client";
import type { Plan } from "@/lib/api/types";

// Each plan object gets its own cache entry; a re-plan is a new object.
const planIds = new WeakMap<Plan, number>();
let nextPlanId = 0;
const planKey = (plan: Plan) => {
  if (!planIds.has(plan)) planIds.set(plan, ++nextPlanId);
  return planIds.get(plan)!;
};

/** The 48-hour corridor grid for a plan. Fetched right after the plan, so routes render first. */
export function useCorridorForecast(plan: Plan | null) {
  return useQuery({
    queryKey: ["corridor", plan ? planKey(plan) : 0],
    enabled: plan !== null,
    staleTime: Infinity,
    // A 4xx (too large a corridor, a rate limit) fails the same way if sent again at once.
    retry: (failureCount, error) => failureCount < 1 && isTransient(error),
    queryFn: ({ signal }) =>
      api.corridorForecast(
        {
          lines: plan!.routes.map((r) => r.corridor_line),
          departure: plan!.departure,
          load_weight_lb: plan!.load_weight_lb,
        },
        signal,
      ),
  });
}
