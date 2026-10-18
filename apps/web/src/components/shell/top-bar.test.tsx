import { act, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import { endTour, useActiveTour } from "@/components/tour/tour-state";
import { mockApi } from "@/test/api";
import { ready } from "@/test/fixtures";
import { setUrl } from "@/test/navigation";
import { renderWithApi } from "@/test/render";

import { TopBar } from "./top-bar";

function TourProbe() {
  const tour = useActiveTour();
  return <p>tour {tour ? `${tour.page} step ${tour.step}` : "closed"}</p>;
}

afterEach(() => act(() => endTour()));

describe("Top bar", () => {
  test("phones get the full navigation in a drawer that Escape closes", async () => {
    mockApi().on("GET", "/ready", ready());
    setUrl("/experiments");
    const { user } = renderWithApi(<TopBar />);
    const toggle = screen.getByRole("button", { name: "Open navigation" });
    expect(toggle).toHaveAttribute("aria-expanded", "false");

    await user.click(toggle);
    const drawer = screen.getByRole("dialog", { name: "Navigation" });
    expect(toggle).toHaveAttribute("aria-expanded", "true");
    for (const label of ["Overview", "Experiments", "Applications", "Services", "Reports", "How it works", "Help", "Settings", "Support", "About"]) {
      expect(within(drawer).getByRole("link", { name: label })).toBeInTheDocument();
    }
    expect(within(drawer).getByRole("link", { name: "Experiments" })).toHaveAttribute("aria-current", "page");
    expect(within(drawer).getByRole("button", { name: "Close navigation" })).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument();
    expect(toggle).toHaveFocus();
  });

  test("navigating closes the drawer", async () => {
    mockApi().on("GET", "/ready", ready());
    setUrl("/");
    const { user } = renderWithApi(<TopBar />);
    await user.click(screen.getByRole("button", { name: "Open navigation" }));
    await user.click(within(screen.getByRole("dialog")).getByRole("link", { name: "Help" }));
    expect(screen.queryByRole("dialog", { name: "Navigation" })).not.toBeInTheDocument();
  });

  test("Tour starts the current page's tour; Help opens that page's help", async () => {
    setUrl("/applications");
    const { user } = renderWithApi(
      <>
        <TopBar />
        <TourProbe />
      </>,
    );
    expect(screen.getByText("tour closed")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Tour of this page" }));
    expect(screen.getByText("tour applications step 0")).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: "Help" }));
    const panel = screen.getByRole("dialog", { name: "Applications" });
    expect(panel).toHaveTextContent("Experiment eligibility");
    expect(within(panel).getByRole("link", { name: /Onboarding runbook/ })).toHaveAttribute(
      "href",
      expect.stringContaining("docs/onboarding.md"),
    );
    expect(within(panel).getByRole("link", { name: "All page guides" })).toHaveAttribute("href", "/help#page-applications");
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toHaveTextContent("Applications");
  });

  test("pages without a tour offer only Help", () => {
    setUrl("/services");
    renderWithApi(<TopBar />);
    expect(screen.queryByRole("button", { name: "Tour of this page" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Help" })).toBeInTheDocument();
  });
});

describe("Breadcrumbs", () => {
  test.each([
    ["/experiments/854cf356-56e1-4ce1-833f-7bcbe3550db8", "854cf356"],
    ["/services/shop/Deployment/checkout", "shop/checkout"],
    ["/how-it-works", "How it works"],
    ["/applications/import", "Import"],
    ["/applications/imports/5b1d3c2e-8a4f-4c6e-9d7a-1f2e3d4c5b6a", "Import 5b1d3c2e"],
    ["/no-such-page", "Not found"],
    ["/_not-found", "Not found"],
    ["/settings/extra", "Not found"],
  ])("%s ends at %s", (url, label) => {
    setUrl(url);
    renderWithApi(<TopBar />);
    expect(within(screen.getByRole("navigation", { name: "Breadcrumb" })).getByText(label)).toHaveAttribute("aria-current", "page");
  });
});
