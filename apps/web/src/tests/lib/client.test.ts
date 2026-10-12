import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, fieldMessages } from "@/lib/api/client";

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
