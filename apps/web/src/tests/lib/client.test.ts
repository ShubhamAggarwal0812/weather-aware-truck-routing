import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, canRetryLater, fieldMessages, isTransient } from "@/lib/api/client";

afterEach(() => vi.unstubAllGlobals());

function respond(status: number, body: unknown) {
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } })),
  );
}

describe("api client", () => {
  it("returns data on success", async () => {
    respond(200, { results: [{ label: "Denver, CO", lat: 39.7, lon: -105 }] });
    await expect(api.searchPlaces("denver")).resolves.toEqual([{ label: "Denver, CO", lat: 39.7, lon: -105 }]);
  });

  it("turns API errors into ApiError with fields", async () => {
    respond(400, { error: "Some fields are invalid.", fields: { load_weight_lb: ["Too big."] } });
    const err = await api.planTrip({} as never).catch((e) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err.status).toBe(400);
    expect(err.message).toBe("Some fields are invalid.");
    expect(fieldMessages(err.fields)).toEqual(["load weight lb: Too big."]);
  });

  it("reports network failures plainly", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))),
    );
    await expect(api.searchPlaces("denver")).rejects.toThrow("Can't reach the server");
  });
});

describe("retrying", () => {
  const failures = {
    network: new ApiError("Can't reach the server.", 0),
    invalid: new ApiError("Some fields are invalid.", 400),
    tooLarge: new ApiError("These routes cover too much ground for the weather heatmap.", 422),
    rateLimited: new ApiError("Request was throttled.", 429),
    unavailable: new ApiError("The weather service is unavailable.", 503),
    unexpected: new Error("Something else broke."),
  };

  it("should resend at once only what the network or the server failed", () => {
    expect(isTransient(failures.network)).toBe(true);
    expect(isTransient(failures.unavailable)).toBe(true);
    expect(isTransient(failures.unexpected)).toBe(true);
    expect(isTransient(failures.invalid)).toBe(false);
    expect(isTransient(failures.tooLarge)).toBe(false);
    expect(isTransient(failures.rateLimited)).toBe(false);
  });

  it("should offer a later retry for a rate limit too, but never for a request the API refuses outright", () => {
    expect(canRetryLater(failures.rateLimited)).toBe(true);
    expect(canRetryLater(failures.unavailable)).toBe(true);
    expect(canRetryLater(failures.invalid)).toBe(false);
    expect(canRetryLater(failures.tooLarge)).toBe(false);
  });
});
