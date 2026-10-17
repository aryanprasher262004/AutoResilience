import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { checkout, copy, fragile, rejection } from "@/test/recordings";

import { ClientImpactPanel, ProvenanceRows, RecordingBanner, ScorePanel, ValidationChecks } from "./evidence";

describe("evidence panels (committed recordings)", () => {
  it("labels every recording as recorded development evidence", () => {
    render(<RecordingBanner recording={fragile()} />);
    const note = screen.getByRole("note");
    expect(within(note).getByText("Recorded experiment")).toBeInTheDocument();
    expect(within(note).getByText("Development run")).toBeInTheDocument();
    expect(within(note).getByText("Unclassified evidence")).toBeInTheDocument();
    expect(note).toHaveTextContent("not controlled research evidence");
    expect(note).toHaveTextContent("Nothing is executed");
  });

  it("does not call a refused experiment a run", () => {
    render(<RecordingBanner recording={rejection()} />);
    expect(screen.getByRole("note")).toHaveTextContent("A real safety validation recorded");
    expect(screen.getByRole("note")).not.toHaveTextContent("A real run");
  });

  it("explains the score with every component and the methodology version", () => {
    const data = fragile();
    render(<ScorePanel recording={data} />);
    expect(screen.getByText("83.7")).toBeInTheDocument();
    expect(screen.getByText(data.experiment.score.explanation)).toBeInTheDocument();
    for (const name of ["Recovery time", "Client outage", "Request failures", "Restarts", "Litmus verdict"]) {
      expect(screen.getByText(name)).toBeInTheDocument();
    }
    expect(screen.getByText(/−14\.4/)).toBeInTheDocument(); // request failures lost points
    expect(screen.getByRole("link", { name: /how it is computed/ })).toHaveAttribute(
      "href",
      expect.stringContaining("docs/scoring/resilience-score-v3.md"),
    );
  });

  it("shows the client's recorded failures and outage", () => {
    render(<ClientImpactPanel recording={fragile()} />);
    expect(screen.getByText("817")).toBeInTheDocument();
    expect(screen.getByText("CONTINUOUS")).toBeInTheDocument();
    expect(screen.getByText("8.369 s")).toBeInTheDocument();
  });

  it("says when the client was not measured", () => {
    const partial = copy(checkout());
    partial.experiment.impact.client = null;
    render(<ClientImpactPanel recording={partial} />);
    expect(screen.getByText(/No client-side load generator measured this workload/)).toBeInTheDocument();
  });

  it("shows provenance with the integrity hash", () => {
    const data = checkout();
    render(<ProvenanceRows recording={data} />);
    expect(screen.getByText(data.integrity.content_sha256)).toBeInTheDocument();
    expect(screen.getByText("No, a real run")).toBeInTheDocument();
  });

  it("highlights the safety check that refused an experiment", () => {
    render(<ValidationChecks recording={rejection()} />);
    const row = screen.getByText("min_healthy_replicas_after_fault").closest("tr")!;
    expect(within(row).getByText("FAILED")).toBeInTheDocument();
    expect(row).toHaveTextContent("0 remaining < minimum 1");
  });
});
