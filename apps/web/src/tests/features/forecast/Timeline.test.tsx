import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Timeline } from "@/features/forecast/components/Timeline";
import { plan } from "../../fixtures/plan";

const json = (status: number, body: unknown) =>
  new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });

let corridorResponse: () => Response;
let corridorRequests: number;

beforeEach(() => {
  corridorRequests = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async () => {
      corridorRequests++;
      return corridorResponse();
    }),
  );
});
afterEach(() => vi.unstubAllGlobals());

function renderTimeline() {
  render(
    <QueryClientProvider client={new QueryClient()}>
      <Timeline plan={plan()} />
    </QueryClientProvider>,
  );
}

describe("Timeline", () => {
  it("should neither resend nor offer to retry a corridor the API calls too large", async () => {
    corridorResponse = () => json(422, { error: "These routes cover too much ground for the weather heatmap." });
    renderTimeline();
    expect(await screen.findByRole("alert")).toHaveTextContent("too much ground");
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
    expect(corridorRequests).toBe(1);
  });

  it("should resend once and offer a retry when the weather service is down", async () => {
    corridorResponse = () => json(503, { error: "The weather service is unavailable. Try again in a minute." });
    renderTimeline();
    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("unavailable"), { timeout: 4000 });
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(corridorRequests).toBe(2);
  });

  it("should offer a retry, without resending at once, after a rate limit", async () => {
    corridorResponse = () => json(429, { error: "Request was throttled. Expected available in 20 seconds." });
    renderTimeline();
    expect(await screen.findByRole("alert")).toHaveTextContent("throttled");
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    expect(corridorRequests).toBe(1);
  });
});
