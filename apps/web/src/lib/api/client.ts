import createClient from "openapi-fetch";
import type { paths } from "../../generated/api";
import type { AppConfig, Corridor, CorridorRequest, Place, Plan, PlanRequest } from "./types";

export class ApiError extends Error {
  readonly status: number;
  readonly fields?: Record<string, unknown>;

  constructor(message: string, status: number, fields?: Record<string, unknown>) {
    super(message);
    this.status = status;
    this.fields = fields;
  }
}

export function isTransient(error: unknown): boolean {
  return !(error instanceof ApiError) || error.status === 0 || error.status >= 500;
}

export function canRetryLater(error: unknown): boolean {
  return isTransient(error) || (error instanceof ApiError && error.status === 429);
}

// Same origin in every environment: Vite proxies /api in development, Vercel/nginx in production.
const client = createClient<paths>({
  baseUrl: import.meta.env.VITE_API_BASE ?? window.location.origin,
  // Look fetch up per call (not once at import) so it can be swapped in tests.
  fetch: (request) => globalThis.fetch(request),
});

type Result<T> = { data?: T; error?: unknown; response: Response };

async function unwrap<T>(call: Promise<Result<T>>): Promise<T> {
  let result: Result<T>;
  try {
    result = await call;
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
  }
  const { data, error, response } = result;
  if (error !== undefined || data === undefined) {
    const body = (error ?? {}) as { error?: string; fields?: Record<string, unknown> };
    throw new ApiError(body.error ?? `Request failed (${response.status}).`, response.status, body.fields);
  }
  return data;
}

export const api = {
  config: (signal?: AbortSignal): Promise<AppConfig> => unwrap(client.GET("/api/v1/config", { signal })),
  searchPlaces: (q: string, signal?: AbortSignal): Promise<Place[]> =>
    unwrap(client.GET("/api/v1/places", { params: { query: { q } }, signal })).then((r) => r.results),
  planTrip: (body: PlanRequest): Promise<Plan> => unwrap(client.POST("/api/v1/trips/plan", { body })),
  corridorForecast: (body: CorridorRequest, signal?: AbortSignal): Promise<Corridor> =>
    unwrap(client.POST("/api/v1/trips/corridor-forecast", { body, signal })),
};

/** Flattens DRF's nested field errors into "field: message" lines. */
export function fieldMessages(fields: Record<string, unknown> | undefined): string[] {
  if (!fields) return [];
  const out: string[] = [];
  const walk = (value: unknown, path: string) => {
    if (typeof value === "string") out.push(path ? `${path}: ${value}` : value);
    else if (Array.isArray(value)) value.forEach((v) => walk(v, path));
    else if (value && typeof value === "object")
      Object.entries(value).forEach(([k, v]) => walk(v, k === "non_field_errors" ? path : k.replaceAll("_", " ")));
  };
  walk(fields, "");
  return out;
}
