import { act, fireEvent, render, screen, within } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { copy, fragile } from "@/test/recordings";

import { Replay } from "./replay";

const pod = (name: string) => screen.getAllByText(name, { selector: "p" })[0].closest("li")!;

describe("Replay", () => {
  afterEach(() => vi.useRealTimers());

  it("starts paused at the recorded start", () => {
    render(<Replay recording={fragile()} />);
    expect(screen.getByRole("button", { name: "Play" })).toHaveAttribute("aria-pressed", "false");
    expect(screen.getByRole("heading", { name: "At T+0.0 s" })).toBeInTheDocument();
    expect(within(screen.getByRole("navigation", { name: "Lifecycle phases" })).getByRole("button", { name: /Validate/ })).toHaveAttribute(
      "aria-current",
      "step",
    );
    expect(pod("pod-2")).toHaveAttribute("data-state", "running");
    expect(pod("pod-1")).toHaveAttribute("data-state", "absent");
    expect(screen.getByText("Computed at completion")).toBeInTheDocument();
  });

  it("steps through recorded events with Next and Prev", () => {
    render(<Replay recording={fragile()} />);
    fireEvent.click(screen.getByRole("button", { name: "Next event" }));
    const current = () => document.querySelector('[aria-current="true"]')?.textContent ?? "";
    expect(current()).toMatch(/Safety validation passed \(8\/8 checks\)/);
    fireEvent.click(screen.getByRole("button", { name: "Next event" }));
    expect(current()).toMatch(/Baseline captured/);
    fireEvent.click(screen.getByRole("button", { name: "Previous event" }));
    expect(current()).toMatch(/Safety validation passed/);
  });

  it("moves one event per press even when presses arrive before a re-render", () => {
    render(<Replay recording={fragile()} />);
    const next = screen.getByRole("button", { name: "Next event" });
    act(() => {
      for (let i = 0; i < 3; i++) next.click();
    });
    expect(document.querySelector('[aria-current="true"]')?.textContent).toMatch(/ChaosEngine created for pod-2/);
  });

  it("jumps to a phase and shows the pod states recorded there", () => {
    render(<Replay recording={fragile()} />);
    const phases = screen.getByRole("navigation", { name: "Lifecycle phases" });
    fireEvent.click(within(phases).getByRole("button", { name: /Observe/ }));
    expect(within(phases).getByRole("button", { name: /Observe/ })).toHaveAttribute("aria-current", "step");
    expect(pod("pod-2")).toHaveAttribute("data-state", "deleted");
    expect(pod("pod-1")).toHaveAttribute("data-state", "starting");
  });

  it("seeks with the slider and shows the final evidence at the end", () => {
    const data = fragile();
    render(<Replay recording={data} />);
    const slider = screen.getByRole("slider", { name: "Replay position" });
    fireEvent.change(slider, { target: { value: slider.getAttribute("max") } });
    expect(slider).toHaveAttribute("aria-valuetext", expect.stringMatching(/Score phase: COMPLETED, scored 83\.7/));
    expect(pod("pod-1")).toHaveAttribute("data-state", "ready");
    expect(screen.getByText(`${data.experiment.recovery.time_to_recovery_seconds} s`)).toBeInTheDocument();
    expect(screen.getByText(/Outage ended after 8\.369 s/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Replay again" })).toBeInTheDocument();
  });

  it("plays recorded time at the chosen speed, pauses and restarts", () => {
    vi.useFakeTimers({ toFake: ["requestAnimationFrame", "cancelAnimationFrame", "performance"] });
    render(<Replay recording={fragile()} />);
    fireEvent.change(screen.getByRole("combobox", { name: "Speed" }), { target: { value: "10" } });
    fireEvent.click(screen.getByRole("button", { name: "Play" }));
    expect(screen.getByRole("button", { name: "Pause" })).toHaveAttribute("aria-pressed", "true");
    act(() => vi.advanceTimersByTime(3000)); // 3 s at 10x = 30 s of recorded time
    expect(screen.getByRole("heading", { name: /At T\+(29|30)\.\d s/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Pause" }));
    const paused = screen.getByRole("heading", { name: /^At / }).textContent;
    act(() => vi.advanceTimersByTime(3000));
    expect(screen.getByRole("heading", { name: /^At / }).textContent).toBe(paused);
    fireEvent.click(screen.getByRole("button", { name: "Restart" }));
    expect(screen.getByRole("heading", { name: "At T+0.0 s" })).toBeInTheDocument();
  });

  it("says so when evidence is missing instead of inventing it", () => {
    const partial = copy(fragile());
    partial.experiment.impact.client = null;
    partial.experiment.target_after = null;
    render(<Replay recording={partial} />);
    expect(screen.getAllByText("Not measured").length).toBeGreaterThan(0);
    expect(screen.getByText(/Other replicas were not individually recorded/)).toBeInTheDocument();
    expect(screen.getAllByText("none recorded").length).toBe(2);
  });
});
