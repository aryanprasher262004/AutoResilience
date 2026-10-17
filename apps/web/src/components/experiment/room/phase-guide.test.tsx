import { render, screen } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { ChecksTable } from "@/components/experiment/checks-table";
import { experiment, validation } from "@/test/fixtures";

import { PhaseGuide } from "./phase-guide";

describe("Phase guide", () => {
  test("explains the current phase of an active run", () => {
    render(<PhaseGuide experiment={experiment({ state: "OBSERVING", orchestration: { mode: "auto" } })} />);
    const section = screen.getByRole("region", { name: /What's happening now · Observing/ });
    expect(section).toHaveTextContent("Litmus holds the fault");
    expect(section).toHaveTextContent("Litmus finishes → the recovery rule is applied.");
  });

  test("is not shown once the run has finished", () => {
    render(<PhaseGuide experiment={experiment({ state: "COMPLETED" })} />);
    expect(screen.queryByRole("region")).not.toBeInTheDocument();
  });
});

describe("Checks table", () => {
  test("adds background only to checks that did not pass, beside the server's message", () => {
    const result = validation(false);
    render(<ChecksTable title="Cluster checks" description="" checks={result.cluster_checks} />);
    const failed = result.cluster_checks.filter((c) => c.status !== "PASSED");
    expect(failed.length).toBeGreaterThan(0);
    for (const check of result.cluster_checks) {
      const row = screen.getByText(check.name).closest("tr")!;
      expect(row).toHaveTextContent(check.message);
      if (check.status === "PASSED") expect(row).not.toHaveTextContent("Why this matters");
    }
    expect(screen.getAllByText(/Why this matters/).length).toBe(
      failed.filter((c) => ["min_healthy_replicas_after_fault", "target_workload_exists", "target_has_running_pods"].includes(c.name)).length,
    );
  });
});
