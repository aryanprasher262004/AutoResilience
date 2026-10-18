import { act, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test } from "vitest";

import { endTour, useActiveTour } from "@/components/tour/tour-state";
import { STORAGE_KEY, readPreferences } from "@/lib/preferences";
import { mockApi } from "@/test/api";
import { environment } from "@/test/fixtures";
import { capabilities } from "@/test/import-fixtures";
import { router, setUrl } from "@/test/navigation";
import { renderWithApi } from "@/test/render";
import { DISCOVERY, EXECUTION } from "@/test/topology-fixtures";

import { ClusterAccess } from "./cluster-access";
import { DataAndBackups } from "./data-backups";
import { ImportSettings } from "./import-settings";
import { TourControls } from "./tour-controls";

beforeEach(() => localStorage.clear());
afterEach(() => act(() => endTour()));

describe("Kubernetes access", () => {
  test("lists the configured clusters with what each allows, and how to change it", async () => {
    mockApi().on("GET", "/clusters", { items: [EXECUTION, DISCOVERY] });
    renderWithApi(<ClusterAccess />);
    const list = within(await screen.findByRole("list", { name: "Authorized clusters" }));
    const row = (context: string) => within(list.getByText(context).closest("li")!);
    expect(row(EXECUTION.context!).getByText("Experiments allowed")).toBeInTheDocument();
    expect(row(DISCOVERY.context!).getByText("No experiments")).toBeInTheDocument();
    expect(row(DISCOVERY.context!).getByText(new RegExp(`limited to ${DISCOVERY.namespaces!.join(", ")}`))).toBeInTheDocument();
    expect(screen.getByText(/terminal-only, so this browser can never widen it/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument(); // explanations only, no controls
  });
});

describe("Data and backups", () => {
  test("local stack: the data volume, backups and terminal-only restore", async () => {
    mockApi().on("GET", "/environment", environment());
    renderWithApi(<DataAndBackups />);
    expect(await screen.findByText("Docker volume autoresilience-data")).toBeInTheDocument();
    expect(screen.getByText(/backs\s+up the current data first/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });

  test("development: your own database, not ar backups", async () => {
    mockApi().on("GET", "/environment", environment({ runtime_mode: "development" }));
    renderWithApi(<DataAndBackups />);
    expect(await screen.findByText("your PostgreSQL (DATABASE_URL)")).toBeInTheDocument();
  });
});

function TourProbe() {
  const tour = useActiveTour();
  return <p>tour {tour ? tour.page : "closed"}</p>;
}

describe("Guided tours", () => {
  test("shows each page's progress; reset and replay", async () => {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ version: 1, tours: { overview: { status: "completed", at: "2026-10-19T08:00:00Z" }, settings: { status: "skipped", at: "2026-10-19T08:00:00Z" } } }),
    );
    setUrl("/settings");
    const { user } = renderWithApi(
      <>
        <TourControls />
        <TourProbe />
      </>,
    );
    const row = (title: string) => within(within(screen.getByRole("list", { name: "Page tours" })).getByText(title).closest("li")!);
    expect(row("Overview").getByText("Finished")).toBeInTheDocument();
    expect(row("Experiments").getByText("Not seen")).toBeInTheDocument();
    expect(row("Application topology").getByText(/next time you open an application/)).toBeInTheDocument();
    expect(row("Application topology").queryByRole("button", { name: "Replay" })).not.toBeInTheDocument();

    await user.click(row("Settings").getByRole("button", { name: "Replay" }));
    expect(screen.getByText("tour settings")).toBeInTheDocument(); // this page: starts in place

    await user.click(row("Overview").getByRole("button", { name: "Replay" }));
    expect(readPreferences().tours.overview).toBeUndefined(); // reset, so it opens there
    expect(router.push).toHaveBeenCalledWith("/");

    await user.click(screen.getByRole("button", { name: "Reset all" }));
    expect(readPreferences().tours).toEqual({});
  });
});

describe("Application imports", () => {
  test("says whether imports can be deployed and how to enable it, with no controls", async () => {
    mockApi().on("GET", "/imports/capabilities", capabilities(false));
    renderWithApi(<ImportSettings />);
    expect(await screen.findByText("Review only")).toBeInTheDocument();
    expect(screen.getByText(/imports can be reviewed and saved, not deployed/)).toBeInTheDocument();
    expect(screen.getByText(/an admission policy rejects any write by the provisioner/)).toBeInTheDocument();
    expect(screen.queryByRole("button")).not.toBeInTheDocument();
  });
});
