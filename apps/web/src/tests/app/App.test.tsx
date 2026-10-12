import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "@/app/App";
import { RULES, plan } from "../fixtures/plan";

// MapLibre needs WebGL, which jsdom doesn't have.
vi.mock("@/features/route-map/MapView", () => ({ default: () => null }));

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let planResponse: () => Promise<Response>;

beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn(() => ({ matches: false, addEventListener: vi.fn(), removeEventListener: vi.fn() })),
  );
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/config") return json(200, { routing_provider: "osrm", truck_aware: false, rules: RULES });
      if (path === "/api/v1/trips/plan") return planResponse();
      if (path === "/api/v1/trips/corridor-forecast") return new Promise<Response>(() => {});
      return json(404, { error: "Not found." });
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderApp() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <App />
    </QueryClientProvider>,
  );
}

async function submitExampleTrip() {
  await userEvent.click(screen.getByRole("button", { name: "Denver → Chicago" }));
  await userEvent.click(screen.getByRole("button", { name: "Find the safest route" }));
}

const unavailable = () => json(503, { error: "The weather service is unavailable. Try again in a minute." });

describe("App", () => {
  it("should keep the previous plan up while re-planning and after a failed re-plan", async () => {
    renderApp();
    planResponse = async () => json(200, plan());
    await submitExampleTrip();
    const headline = await screen.findByText("Route B is the safest option.");

    let fail!: () => void;
    planResponse = () =>
      new Promise((resolve) => {
        fail = () => resolve(unavailable());
      });
    await userEvent.click(screen.getByRole("button", { name: "Find the safest route" }));
    await waitFor(() => expect(headline.closest(".transition-opacity")).toHaveClass("opacity-50"));
    expect(headline).toBeInTheDocument();

    fail();
    expect(await screen.findByText(/The weather service is unavailable/)).toBeInTheDocument();
    expect(screen.getByText("The results below are from the previous plan.")).toBeInTheDocument();
    expect(screen.getByText("Route B is the safest option.")).toBeInTheDocument();
    expect(screen.getByText("Route B is the safest option.").closest(".transition-opacity")).not.toHaveClass(
      "opacity-50",
    );
  });

  it("should replace the previous results when a re-plan succeeds", async () => {
    renderApp();
    planResponse = async () => json(200, plan());
    await submitExampleTrip();
    await screen.findByText("Route B is the safest option.");

    const replanned = plan();
    replanned.recommendation = {
      ...replanned.recommendation,
      route_id: "A",
      headline: "Route A is the safest option.",
    };
    planResponse = async () => json(200, replanned);
    await userEvent.click(screen.getByRole("button", { name: "Find the safest route" }));
    expect(await screen.findByText("Route A is the safest option.")).toBeInTheDocument();
    expect(screen.queryByText("Route B is the safest option.")).not.toBeInTheDocument();
  });

  it("should show the error without a previous-plan note when the first plan fails", async () => {
    renderApp();
    planResponse = async () => unavailable();
    await submitExampleTrip();
    expect(await screen.findByText(/The weather service is unavailable/)).toBeInTheDocument();
    expect(screen.queryByText("The results below are from the previous plan.")).not.toBeInTheDocument();
    expect(screen.queryByText("Route B is the safest option.")).not.toBeInTheDocument();
  });
});
