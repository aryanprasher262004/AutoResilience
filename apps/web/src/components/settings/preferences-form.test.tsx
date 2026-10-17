import { screen } from "@testing-library/react";
import { beforeEach, describe, expect, test } from "vitest";

import { BUILT_IN_DEFAULTS, STORAGE_KEY, parsePreferences, readPreferences } from "@/lib/preferences";
import { renderWithApi } from "@/test/render";

import { PreferencesForm } from "./preferences-form";

beforeEach(() => localStorage.clear());

describe("Experiment defaults", () => {
  test("start from the built-in values", () => {
    renderWithApi(<PreferencesForm />);
    expect(screen.getByLabelText("Deletion mode")).toHaveValue("GRACEFUL");
    expect(screen.getByLabelText("Duration (seconds)")).toHaveValue(60);
    expect(screen.getByLabelText("Affected replicas")).toHaveValue(1);
  });

  test("saves valid values to this browser", async () => {
    const { user } = renderWithApi(<PreferencesForm />);
    await user.selectOptions(screen.getByLabelText("Deletion mode"), "FORCE");
    await user.clear(screen.getByLabelText("Duration (seconds)"));
    await user.type(screen.getByLabelText("Duration (seconds)"), "120");
    await user.click(screen.getByRole("button", { name: "Save defaults" }));

    expect(screen.getByRole("status")).toHaveTextContent("Saved");
    expect(readPreferences().experimentDefaults).toEqual({ durationSeconds: 120, affectedReplicas: 1, mode: "FORCE" });
  });

  test("rejects obviously invalid input without saving, and leaves limits to the server", async () => {
    const { user } = renderWithApi(<PreferencesForm />);
    await user.clear(screen.getByLabelText("Affected replicas"));
    await user.type(screen.getByLabelText("Affected replicas"), "0");
    await user.click(screen.getByRole("button", { name: "Save defaults" }));

    expect(screen.getByText("Whole number, > 0")).toBeInTheDocument();
    expect(screen.getByLabelText("Affected replicas")).toHaveAttribute("aria-invalid", "true");
    expect(localStorage.getItem(STORAGE_KEY)).toBeNull();

    // A large value is not second-guessed here: the namespace policy decides at the safety check.
    await user.clear(screen.getByLabelText("Affected replicas"));
    await user.type(screen.getByLabelText("Affected replicas"), "50");
    await user.click(screen.getByRole("button", { name: "Save defaults" }));
    expect(readPreferences().experimentDefaults.affectedReplicas).toBe(50);
    expect(screen.getByText(/These are starting values, not permissions/)).toBeInTheDocument();
  });

  test("reset restores the built-in values", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, experimentDefaults: { durationSeconds: 30, affectedReplicas: 2, mode: "FORCE" } }));
    const { user } = renderWithApi(<PreferencesForm />);
    expect(screen.getByLabelText("Duration (seconds)")).toHaveValue(30);
    await user.click(screen.getByRole("button", { name: "Reset to defaults" }));
    expect(readPreferences().experimentDefaults).toEqual(BUILT_IN_DEFAULTS);
    expect(screen.getByLabelText("Duration (seconds)")).toHaveValue(60);
  });
});

describe("parsePreferences", () => {
  test("falls back field by field on malformed or tampered storage", () => {
    expect(parsePreferences("not json")).toEqual(parsePreferences(null));
    expect(
      parsePreferences(JSON.stringify({ experimentDefaults: { durationSeconds: -5, affectedReplicas: 2.5, mode: "NUKE" }, guideDismissedAt: 7 })),
    ).toEqual({ version: 1, experimentDefaults: BUILT_IN_DEFAULTS, guideDismissedAt: null });
    expect(parsePreferences(JSON.stringify({ experimentDefaults: { durationSeconds: 90 } })).experimentDefaults).toEqual({
      ...BUILT_IN_DEFAULTS,
      durationSeconds: 90,
    });
  });
});
