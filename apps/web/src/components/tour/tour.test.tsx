import { act, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test, vi } from "vitest";

import { PAGE_HELP, TOUR_TARGET, type TourTarget } from "@/lib/help-content";
import { STORAGE_KEY, readPreferences } from "@/lib/preferences";
import { router, setUrl } from "@/test/navigation";
import { renderWithApi } from "@/test/render";

import { TourHost } from "./tour";
import { endTour, startTour } from "./tour-state";

const RECT = { top: 120, left: 80, width: 240, height: 40, bottom: 160, right: 320, x: 80, y: 120 };
const ZERO = { top: 0, left: 0, width: 0, height: 0, bottom: 0, right: 0, x: 0, y: 0 };

/** happy-dom does no layout: marked targets get a box unless the test hides them. */
beforeEach(() => {
  localStorage.clear();
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const shown = this.dataset.tour && !this.hasAttribute("data-test-hidden");
    return { ...(shown ? RECT : ZERO), toJSON: () => ({}) } as DOMRect;
  });
});
afterEach(() => act(() => endTour()));

function Page({ targets, hidden = [] }: { targets: TourTarget[]; hidden?: TourTarget[] }) {
  return (
    <>
      {targets.map((t) => (
        <div key={t} data-tour={t} data-test-hidden={hidden.includes(t) ? "" : undefined}>
          <button type="button">control {t}</button>
        </div>
      ))}
      <TourHost />
    </>
  );
}

const card = () => screen.getByRole("dialog");
const open = () => screen.findByRole("dialog", {}, { timeout: 2000 });

describe("Page tours", () => {
  test("open on the first visit to a page, on that page's tour, with focus on the step", async () => {
    setUrl("/applications");
    renderWithApi(<Page targets={Object.values(TOUR_TARGET)} />);
    const dialog = await open();
    expect(dialog).toHaveAccessibleName("What onboarding means");
    expect(dialog).toHaveTextContent(`Tour · Applications · 1 of ${PAGE_HELP.applications.tour!.length}`);
    expect(screen.getByRole("heading", { name: "What onboarding means" })).toHaveFocus();
    expect(await screen.findByTestId("tour-spotlight")).toBeInTheDocument();
  });

  test("Next, Back and the step dots move through it; Finish is remembered", async () => {
    setUrl("/settings");
    const { user, unmount } = renderWithApi(<Page targets={Object.values(TOUR_TARGET)} />);
    await open();
    await user.click(screen.getByRole("button", { name: "Next" }));
    expect(card()).toHaveAccessibleName("Environment health");
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(card()).toHaveAccessibleName("Settings at a glance");
    const steps = PAGE_HELP.settings.tour!;
    await user.click(screen.getByRole("button", { name: `Step ${steps.length}: ${steps.at(-1)!.title}` }));
    expect(screen.getByRole("button", { name: `Step ${steps.length}: ${steps.at(-1)!.title}` })).toHaveAttribute("aria-current", "step");
    await user.click(screen.getByRole("button", { name: "Finish" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(readPreferences().tours.settings).toEqual({ status: "completed", at: expect.any(String) });
    unmount();
    renderWithApi(<Page targets={[]} />);
    await new Promise((r) => setTimeout(r, 900));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  test("Skip and Escape close it and are remembered as skipped", async () => {
    setUrl("/");
    const { user } = renderWithApi(<Page targets={[]} />);
    await open();
    await user.click(screen.getByRole("button", { name: "Skip tour" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(readPreferences().tours.overview?.status).toBe("skipped");

    act(() => startTour("overview"));
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!).tours.overview.status).toBe("skipped");
  });

  test("arrow keys step through it from the card", async () => {
    setUrl("/");
    const { user } = renderWithApi(<Page targets={[]} />);
    await open();
    await user.keyboard("{ArrowRight}");
    expect(card()).toHaveAccessibleName("Safety is enforced by the server");
    await user.keyboard("{ArrowLeft}");
    expect(card()).toHaveAccessibleName("Welcome to AutoResilience");
  });

  test("a control that is not on screen is said so, with the reason", async () => {
    setUrl("/");
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, tours: { overview: { status: "skipped", at: "x" } } }));
    renderWithApi(<Page targets={[TOUR_TARGET.navNewExperiment]} hidden={[TOUR_TARGET.navNewExperiment]} />);
    const step = PAGE_HELP.overview.tour!.findIndex((s) => s.target === TOUR_TARGET.overviewOutcomes);
    act(() => startTour("overview", step));
    const status = await within(card()).findByRole("status", {}, { timeout: 2000 });
    expect(status).toHaveTextContent("Not on screen right now. These counts appear after your first experiment.");
    expect(screen.queryByTestId("tour-spotlight")).not.toBeInTheDocument();
    // A target hidden by the responsive layout counts as missing too.
    await screen.findByRole("button", { name: "Next" });
    await act(async () => startTour("overview", PAGE_HELP.overview.tour!.findIndex((s) => s.target === TOUR_TARGET.navNewExperiment)));
    expect(await within(card()).findByRole("status", {}, { timeout: 2000 })).toHaveTextContent("menu (top left)");
  });

  test("a safe view control can be used and moves the tour on; others stay covered", async () => {
    setUrl("/applications/7d2f");
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, tours: { topology: { status: "skipped", at: "x" } } }));
    const { user } = renderWithApi(<Page targets={Object.values(TOUR_TARGET)} />);
    const steps = PAGE_HELP.topology.tour!;
    act(() => startTour("topology", 0));
    await waitFor(() => expect(screen.getByTestId("tour-spotlight")).toHaveClass("pointer-events-auto")); // not an advance step

    const kinds = steps.findIndex((s) => s.target === TOUR_TARGET.topologyKinds);
    act(() => startTour("topology", kinds));
    await waitFor(() => expect(screen.getByTestId("tour-spotlight")).toHaveClass("pointer-events-none"));
    expect(card()).toHaveTextContent(steps[kinds].tryIt!);
    await user.click(screen.getByRole("button", { name: `control ${TOUR_TARGET.topologyKinds}` }));
    await waitFor(() => expect(card()).toHaveAccessibleName(steps[kinds + 1].title));
  });

  test("leaving the page ends its tour unrecorded, and the next page's tour starts", async () => {
    setUrl("/experiments");
    renderWithApi(<Page targets={Object.values(TOUR_TARGET)} />);
    expect(await open()).toHaveAccessibleName("Your experiment history");
    act(() => router.push("/settings"));
    expect(await open()).toHaveAccessibleName("Settings at a glance");
    expect(readPreferences().tours.experiments).toBeUndefined();
  });

  test("pages without a tour never show one", async () => {
    setUrl("/services");
    renderWithApi(<Page targets={[]} />);
    await new Promise((r) => setTimeout(r, 900));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
