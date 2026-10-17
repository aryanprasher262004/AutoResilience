import { act, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, test } from "vitest";

import { closeGuide, useGuideOpen } from "@/components/onboarding/guide-state";
import { mockApi } from "@/test/api";
import { ready } from "@/test/fixtures";
import { setUrl } from "@/test/navigation";
import { renderWithApi } from "@/test/render";

import { TopBar } from "./top-bar";

function GuideProbe() {
  return <p>guide {useGuideOpen() ? "open" : "closed"}</p>;
}

afterEach(() => act(() => closeGuide()));

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
    for (const label of ["Overview", "Experiments", "Services", "Reports", "How it works", "Help", "Settings", "Support", "About"]) {
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

  test("Guide replays the getting-started guide; Help links to the help page", async () => {
    setUrl("/services");
    const { user } = renderWithApi(
      <>
        <TopBar />
        <GuideProbe />
      </>,
    );
    expect(screen.getByText("guide closed")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Guide" }));
    expect(screen.getByText("guide open")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Help" })).toHaveAttribute("href", "/help");
    expect(screen.getByRole("navigation", { name: "Breadcrumb" })).toHaveTextContent("Services");
  });
});

describe("Breadcrumbs", () => {
  test.each([
    ["/experiments/854cf356-56e1-4ce1-833f-7bcbe3550db8", "854cf356"],
    ["/services/shop/Deployment/checkout", "shop/checkout"],
    ["/how-it-works", "How it works"],
    ["/no-such-page", "Not found"],
    ["/_not-found", "Not found"],
    ["/settings/extra", "Not found"],
  ])("%s ends at %s", (url, label) => {
    setUrl(url);
    renderWithApi(<TopBar />);
    expect(within(screen.getByRole("navigation", { name: "Breadcrumb" })).getByText(label)).toHaveAttribute("aria-current", "page");
  });
});
