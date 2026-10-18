import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, test, vi } from "vitest";

import { Tooltip, VIEWPORT_MARGIN, placeTooltip } from "./tooltip";

const TIP = { width: 240, height: 48 };

describe("placeTooltip", () => {
  test("above the control when there is room, aligned with it", () => {
    const p = placeTooltip({ top: 300, left: 100, width: 80, height: 28 }, TIP, { width: 1440, height: 900 });
    expect(p).toMatchObject({ side: "top", left: 100, top: 300 - 6 - 48 });
  });

  test("flips below near the top edge (e.g. the first filter row under the header)", () => {
    const p = placeTooltip({ top: 20, left: 100, width: 80, height: 28 }, TIP, { width: 1440, height: 900 });
    expect(p.side).toBe("bottom");
    expect(p.top).toBe(20 + 28 + 6);
  });

  test("shifts left near the right edge so the end is never cut off (the `slice for` toggle)", () => {
    const p = placeTooltip({ top: 300, left: 1380, width: 70, height: 28 }, TIP, { width: 1440, height: 900 });
    expect(p.left + TIP.width).toBeLessThanOrEqual(1440 - VIEWPORT_MARGIN);
    expect(p.left).toBe(1440 - VIEWPORT_MARGIN - TIP.width);
  });

  test.each([
    ["phone", 390],
    ["narrow phone", 320],
    ["tablet", 768],
  ])("stays inside a %s viewport and wraps instead of overflowing", (_, width) => {
    const p = placeTooltip({ top: 400, left: width - 40, width: 60, height: 28 }, { width: 400, height: 80 }, { width, height: 800 });
    expect(p.maxWidth).toBeLessThanOrEqual(width - 2 * VIEWPORT_MARGIN);
    expect(p.left).toBeGreaterThanOrEqual(VIEWPORT_MARGIN);
    expect(p.left + Math.min(400, p.maxWidth)).toBeLessThanOrEqual(width - VIEWPORT_MARGIN);
  });

  test("never above the viewport when neither side fits", () => {
    const p = placeTooltip({ top: 30, left: 10, width: 60, height: 28 }, { width: 200, height: 500 }, { width: 400, height: 520 });
    expect(p.top).toBeGreaterThanOrEqual(VIEWPORT_MARGIN);
  });
});

describe("Tooltip", () => {
  afterEach(() => vi.restoreAllMocks());

  function setup(rect: Partial<DOMRect>) {
    vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
      const box = this.getAttribute("role") === "tooltip" ? { ...TIP, top: 0, left: 0 } : { top: 300, left: 0, width: 70, height: 28, ...rect };
      return { ...box, right: box.left + box.width, bottom: box.top + box.height, x: box.left, y: box.top, toJSON: () => ({}) } as DOMRect;
    });
    return render(
      <div style={{ overflow: "hidden", width: 100 }} data-testid="clipping-parent">
        <Tooltip content="EndpointSlice → Service: the label kubernetes.io/service-name">
          {(describedBy) => (
            <button type="button" aria-describedby={describedBy}>
              slice for
            </button>
          )}
        </Tooltip>
      </div>,
    );
  }

  test("is portalled out of clipping containers, positioned inside the viewport", async () => {
    setup({ left: window.innerWidth - 60 });
    const user = userEvent.setup();
    await user.hover(screen.getByRole("button", { name: "slice for" }));
    const tip = screen.getByRole("tooltip");
    expect(screen.getByTestId("clipping-parent")).not.toContainElement(tip);
    expect(tip.parentElement).toBe(document.body);
    expect(tip).toHaveClass("fixed", "break-words");
    const left = parseFloat(tip.style.left);
    expect(left + TIP.width).toBeLessThanOrEqual(window.innerWidth - VIEWPORT_MARGIN);
  });

  test("keyboard focus shows it, it describes the control, Escape hides it", async () => {
    setup({});
    const user = userEvent.setup();
    await user.tab();
    const button = screen.getByRole("button", { name: "slice for" });
    expect(button).toHaveFocus();
    expect(screen.getByRole("tooltip")).toBeVisible();
    expect(button).toHaveAccessibleDescription(/kubernetes.io\/service-name/);
    await user.keyboard("{Escape}");
    expect(screen.queryByRole("tooltip")).not.toBeInTheDocument();
    expect(button).toHaveFocus();
  });

  test("re-measures on scroll so it follows its control", async () => {
    setup({ top: 300 });
    const user = userEvent.setup();
    await user.hover(screen.getByRole("button", { name: "slice for" }));
    expect(screen.getByRole("tooltip")).toHaveAttribute("data-side", "top");
    vi.mocked(HTMLElement.prototype.getBoundingClientRect).mockImplementation(function (this: HTMLElement) {
      const box = this.getAttribute("role") === "tooltip" ? { ...TIP, top: 0, left: 0 } : { top: 10, left: 0, width: 70, height: 28 };
      return { ...box, right: 0, bottom: 0, x: 0, y: 0, toJSON: () => ({}) } as DOMRect;
    });
    act(() => {
      fireEvent.scroll(window);
    });
    expect(screen.getByRole("tooltip")).toHaveAttribute("data-side", "bottom");
  });
});
