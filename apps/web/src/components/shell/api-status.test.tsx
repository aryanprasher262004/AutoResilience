import { act, screen } from "@testing-library/react";
import { describe, expect, test, vi } from "vitest";

import { useDashboardSummary } from "@/lib/api/queries";
import { apiError, json, mockApi, networkError, proxyDown } from "@/test/api";
import { dashboard, databaseDown, ready } from "@/test/fixtures";
import { renderWithApi } from "@/test/render";

import { ApiStatus } from "./api-status";

const status = () => screen.getByRole("status");

describe("API status (GET /ready)", () => {
  test("API ready: green, with the readiness detail as tooltip", async () => {
    mockApi().on("GET", "/ready", ready());
    renderWithApi(<ApiStatus />);

    expect(await screen.findByText("API ready")).toBeInTheDocument();
    expect(status().parentElement).toHaveAttribute(
      "title",
      "API ready: localhost:5432/autoresilience at revision 08697f19aec0",
    );
  });

  test("database unavailable: 503 not_ready is shown as a reason, not as 'API unreachable'", async () => {
    mockApi().on("GET", "/ready", () => json(databaseDown(), 503));
    renderWithApi(<ApiStatus detailed />);

    expect(await screen.findByText("Database unavailable")).toBeInTheDocument();
    expect(
      screen.getByText("Cannot connect to localhost:5432/autoresilience: connection failed: Connection refused"),
    ).toBeInTheDocument();
    expect(screen.queryByText(/API ready|API unreachable/)).not.toBeInTheDocument();
  });

  test.each([
    ["the browser cannot reach anything", networkError],
    ["the Next proxy answers a bare 500 (API process down)", proxyDown],
  ])("API unreachable when %s", async (_, handler) => {
    mockApi().on("GET", "/ready", handler);
    renderWithApi(<ApiStatus />);

    expect(await screen.findByText("API unreachable")).toBeInTheDocument();
  });

  test("a JSON error that is not a readiness answer is 'not ready', never 'ready'", async () => {
    mockApi().on("GET", "/ready", () => apiError(404, "Not Found"));
    renderWithApi(<ApiStatus />);

    expect(await screen.findByText("API not ready")).toBeInTheDocument();
  });

  test("recovers to ready and refetches data that failed meanwhile", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const api = mockApi()
      .sequence("GET", "/ready", () => json(databaseDown(), 503), () => json(ready()))
      .sequence(
        "GET",
        "/dashboard/summary",
        () => apiError(503, "Database unavailable at localhost:5432/autoresilience"),
        () => json(dashboard()),
      );
    function DashboardProbe() {
      const { data, isError } = useDashboardSummary();
      return <p>{isError ? "dashboard failed" : data ? `dashboard total ${data.total}` : "loading"}</p>;
    }
    renderWithApi(
      <>
        <ApiStatus />
        <DashboardProbe />
      </>,
    );
    expect(await screen.findByText("Database unavailable")).toBeInTheDocument();
    expect(await screen.findByText("dashboard failed")).toBeInTheDocument();

    // Not ready is re-checked every 5 s.
    await act(() => vi.advanceTimersByTimeAsync(5_000));

    expect(await screen.findByText("API ready")).toBeInTheDocument();
    expect(await screen.findByText("dashboard total 2")).toBeInTheDocument();
    expect(api.requests("GET", "/dashboard/summary")).toHaveLength(2);
  });
});
