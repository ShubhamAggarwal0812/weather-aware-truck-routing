import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { TripForm, validateTrip } from "@/features/trip-planner/components/TripForm";
import { parseCoordinates } from "@/features/trip-planner/components/PlaceInput";

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
