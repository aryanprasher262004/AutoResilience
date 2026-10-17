import { act, screen, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, test } from "vitest";

import { mockApi } from "@/test/api";
import { dashboard, databaseDown, services } from "@/test/fixtures";
import { renderWithApi } from "@/test/render";
import { STORAGE_KEY, readPreferences } from "@/lib/preferences";

import { Guide } from "./guide";
import { closeGuide, openGuide } from "./guide-state";

const dialog = () => screen.getByRole("dialog");

beforeEach(() => localStorage.clear());
afterEach(() => act(() => closeGuide()));

describe("Getting-started guide", () => {
  test("opens on the first visit with focus on the step heading", async () => {
    renderWithApi(<Guide />);

    expect(await screen.findByRole("dialog", { name: "Welcome to AutoResilience" })).toHaveAttribute("aria-modal", "true");
    expect(screen.getByRole("heading", { name: "Welcome to AutoResilience" })).toHaveFocus();
    expect(dialog()).toHaveTextContent("step 1 of 5");
  });

  test("steps forward and back, and the step indicator follows", async () => {
    const { user } = renderWithApi(<Guide />);
    await user.click(await screen.findByRole("button", { name: "Next" }));

    expect(screen.getByRole("heading", { name: "Safety is enforced by the server" })).toHaveFocus();
    expect(screen.getByRole("button", { name: "Step 2: Safety is enforced by the server" })).toHaveAttribute("aria-current", "step");
    expect(dialog()).toHaveTextContent("no setting here can relax a limit");

    await user.click(screen.getByRole("button", { name: "Step 3: What you can test today" }));
    expect(dialog()).toHaveTextContent("GRACEFUL");
    expect(dialog()).toHaveTextContent("FORCE");
    await user.click(screen.getByRole("button", { name: "Back" }));
    expect(screen.getByRole("heading", { name: "Safety is enforced by the server" })).toBeInTheDocument();
  });

  test("skipping closes it and is remembered", async () => {
    const { user } = renderWithApi(<Guide />);
    await user.click(await screen.findByRole("button", { name: "Skip guide" }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(readPreferences().guideDismissedAt).not.toBeNull();
    expect(JSON.parse(localStorage.getItem(STORAGE_KEY)!).guideDismissedAt).toEqual(expect.any(String));
  });

  test("Escape dismisses it", async () => {
    const { user } = renderWithApi(<Guide />);
    await screen.findByRole("dialog");
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(readPreferences().guideDismissedAt).not.toBeNull();
  });

  test("stays closed once dismissed, and can be replayed", async () => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, guideDismissedAt: "2026-10-17T07:00:00Z" }));
    renderWithApi(<Guide />);
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();

    act(() => openGuide());
    expect(await screen.findByRole("dialog", { name: "Welcome to AutoResilience" })).toBeInTheDocument();
  });

  test("keeps keyboard focus inside the dialog", async () => {
    const { user } = renderWithApi(<Guide />);
    await screen.findByRole("dialog");
    const next = screen.getByRole("button", { name: "Next" });
    next.focus();
    await user.tab();
    expect(screen.getByRole("button", { name: "Skip guide" })).toHaveFocus();
    await user.tab({ shift: true });
    expect(next).toHaveFocus();
  });

  test("the last step checks the environment live and links onward", async () => {
    mockApi().on("GET", "/ready", databaseDown()).on("GET", "/services", services()).on("GET", "/dashboard/summary", dashboard());
    const { user } = renderWithApi(<Guide />);
    await user.click(await screen.findByRole("button", { name: "Step 5: Your environment" }));

    const check = (label: string) => within(screen.getByText(label).closest("li")!);
    expect(await check("API and database").findByText("Not ready")).toBeInTheDocument();
    expect(check("API and database").getByText(/Help → Troubleshooting/)).toBeInTheDocument();
    expect(await check("Workloads discovered").findByText(String(services().items.length))).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Create an experiment" })).toHaveAttribute("href", "/experiments/new");

    await user.click(screen.getByRole("button", { name: "Finish" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });
});
