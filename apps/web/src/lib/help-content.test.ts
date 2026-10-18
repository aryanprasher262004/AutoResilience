import { describe, expect, test } from "vitest";

import { PAGE_HELP, type PageId, TOUR_PAGES, TOUR_TARGET, pageFor } from "./help-content";

describe("Help content", () => {
  test.each([
    ["/", "overview"],
    ["/experiments", "experiments"],
    ["/experiments/new", "new-experiment"],
    ["/experiments/854cf356-56e1-4ce1-833f-7bcbe3550db8", "experiment"],
    ["/applications", "applications"],
    ["/applications/new", "onboard"],
    ["/applications/7d2f", "topology"],
    ["/services", "services"],
    ["/services/shop/Deployment/checkout", "service"],
    ["/reports/1", "report"],
    ["/settings", "settings"],
    ["/help", "learn"],
    ["/no-such-page", "learn"],
  ] as [string, PageId][])("%s is the %s page", (path, page) => {
    expect(pageFor(path)).toBe(page);
  });

  test("tours exist for the five main pages", () => {
    expect(TOUR_PAGES).toEqual(["overview", "experiments", "applications", "topology", "settings"]);
  });

  test("tours only advance on view-only controls, never on ones that create, run or approve", () => {
    const viewOnly = new Set<string>([
      TOUR_TARGET.experimentsFilters,
      TOUR_TARGET.topologyGraph,
      TOUR_TARGET.topologyKinds,
      TOUR_TARGET.topologyLegend,
    ]);
    for (const page of TOUR_PAGES) {
      for (const step of PAGE_HELP[page].tour!) {
        if (step.advance) expect(viewOnly, `${page}: ${step.title}`).toContain(step.target);
        if (step.advance) expect(step.tryIt).toBeTruthy();
      }
    }
  });

  test("every tour target is a known control and every page explains itself", () => {
    const known = new Set<string>(Object.values(TOUR_TARGET));
    for (const help of Object.values(PAGE_HELP)) {
      expect(help.summary).toBeTruthy();
      expect(help.topics.length).toBeGreaterThan(0);
      for (const step of help.tour ?? []) if (step.target) expect(known).toContain(step.target);
    }
  });
});
