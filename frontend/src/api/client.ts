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

const BASE = import.meta.env.VITE_API_BASE ?? "/api";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new ApiError("Can't reach the server. Check your connection and try again.", 0);
  }
  const body = await response.json().catch(() => null);
  if (!response.ok) {
    const message = body?.error ?? `Request failed (${response.status}).`;
    throw new ApiError(message, response.status, body?.fields);
  }
  return body as T;
}

export const api = {
  config: () => request<AppConfig>("/config"),
  geocode: (q: string, signal?: AbortSignal) =>
    request<{ results: Place[] }>(`/geocode?q=${encodeURIComponent(q)}`, { signal }).then((r) => r.results),
  plan: (body: PlanRequest) => request<Plan>("/plan", { method: "POST", body: JSON.stringify(body) }),
  corridor: (body: CorridorRequest, signal?: AbortSignal) =>
    request<Corridor>("/corridor", { method: "POST", body: JSON.stringify(body), signal }),
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
