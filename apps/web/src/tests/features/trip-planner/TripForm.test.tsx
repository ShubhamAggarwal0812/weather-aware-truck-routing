import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { TripForm, validateTrip } from "@/features/trip-planner/components/TripForm";
import { parseCoordinates } from "@/features/trip-planner/components/PlaceInput";
import { RULES } from "../../fixtures/plan";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let configResponse: () => Response;
let configRequests: number;

beforeEach(() => {
  configResponse = () => json(200, { routing_provider: "osrm", truck_aware: false, rules: RULES });
  configRequests = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      if (new URL(request.url).pathname !== "/api/v1/config") return json(200, { results: [] });
      configRequests++;
      return configResponse();
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderForm(onSubmit = vi.fn()) {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <TripForm loading={false} onSubmit={onSubmit} />
    </QueryClientProvider>,
  );
  return onSubmit;
}

describe("TripForm", () => {
  it("blocks submit until both places are picked", async () => {
    const onSubmit = renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Find the safest route" }));
    expect(screen.getByRole("alert")).toHaveTextContent("Pick an origin");
    expect(onSubmit).not.toHaveBeenCalled();
  });

  it("submits an example trip with the chosen interval", async () => {
    const onSubmit = renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Denver → Chicago" }));
    await userEvent.click(screen.getByRole("radio", { name: "10 mi" }));
    await userEvent.click(screen.getByRole("button", { name: "Find the safest route" }));
    expect(onSubmit).toHaveBeenCalledTimes(1);
    const request = onSubmit.mock.calls[0][0];
    expect(request.origin.label).toBe("Denver, CO");
    expect(request.destination.label).toBe("Chicago, IL");
    expect(request.load_weight_lb).toBe(42_000);
    expect(request.interval_miles).toBe(10);
    expect(request.rest_breaks).toBe(true);
    expect(new Date(request.departure).getTime()).toBeGreaterThan(Date.now());
  });

  it("swaps origin and destination", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Denver → Chicago" }));
    await userEvent.click(screen.getByRole("button", { name: "Swap origin and destination" }));
    expect(screen.getByLabelText("Origin")).toHaveValue("Chicago, IL");
    expect(screen.getByLabelText("Destination")).toHaveValue("Denver, CO");
  });

  it("should empty a box when a swap moves an unpicked side into it", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Denver → Chicago" }));
    await userEvent.type(screen.getByLabelText("Destination"), "x");
    expect(screen.getByLabelText("Destination")).toHaveValue("Chicago, ILx");
    await userEvent.click(screen.getByRole("button", { name: "Swap origin and destination" }));
    expect(screen.getByLabelText("Origin")).toHaveValue("");
    expect(screen.getByLabelText("Destination")).toHaveValue("Denver, CO");
  });

  it("should leave both boxes empty when swapping two empty sides", async () => {
    renderForm();
    await userEvent.click(screen.getByRole("button", { name: "Swap origin and destination" }));
    expect(screen.getByLabelText("Origin")).toHaveValue("");
    expect(screen.getByLabelText("Destination")).toHaveValue("");
  });

  it("should write the load-rule hint from the server's rules", async () => {
    renderForm();
    expect(
      await screen.findByText(/45\u2060\u2013\u206054 mph wind with a load over 30,000 lb is No Travel\./),
    ).toBeInTheDocument();
    expect(
      screen.getByText(/35\u2060\u2013\u206044 mph wind with a load over 40,000 lb is Severe\./),
    ).toBeInTheDocument();
  });

  it("should keep only the cargo note when the rules can't be loaded", async () => {
    configResponse = () => json(503, { error: "The service is unavailable." });
    renderForm();
    await waitFor(() => expect(configRequests).toBe(2), { timeout: 4000 });
    expect(screen.getByText("Cargo only.")).toBeInTheDocument();
    expect(screen.queryByText(/is No Travel/)).not.toBeInTheDocument();
  });
});

describe("validateTrip", () => {
  const place = { label: "x", lat: 1, lon: 2 };
  const now = new Date("2026-10-12T12:00"); // local time, like datetime-local values
  const base = { origin: place, destination: place, departure: "2026-10-12T15:00", load: "42000" };

  it("accepts a valid trip", () => {
    expect(validateTrip(base, now)).toEqual([]);
  });

  it.each([
    [{ load: "" }, "Load weight"],
    [{ load: "90000" }, "Load weight"],
    [{ departure: "2026-10-01T10:00" }, "past"],
    [{ departure: "2026-10-25T10:00" }, "within 7 days"],
  ])("rejects %o", (change, message) => {
    expect(validateTrip({ ...base, ...change }, now).join(" ")).toContain(message);
  });
});

describe("parseCoordinates", () => {
  it("reads lat, lon pairs and rejects out-of-range values", () => {
    expect(parseCoordinates(" 39.74, -104.99 ")).toEqual({ label: "39.7400, -104.9900", lat: 39.74, lon: -104.99 });
    expect(parseCoordinates("99, 10")).toBeNull();
    expect(parseCoordinates("Denver")).toBeNull();
  });
});
