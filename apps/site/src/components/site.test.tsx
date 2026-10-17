import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HomePage from "@/app/page";
import PlaygroundPage from "@/app/playground/page";
import { navigation } from "@/test/setup";

import { SiteFooter } from "./site-footer";
import { SiteNav } from "./site-nav";
import { Topology } from "./topology";

describe("SiteNav", () => {
  it("lists the six sections in order and marks the current page", () => {
    navigation.pathname = "/how-it-works/";
    render(<SiteNav />);
    const nav = screen.getByRole("navigation", { name: "Main" });
    const desktop = within(nav).getAllByRole("list")[0];
    const labels = within(desktop).getAllByRole("link").map((link) => link.textContent);
    expect(labels).toEqual(["Product", "How It Works", "Playground", "Docs", "Download", "About"]);
    expect(within(desktop).getByRole("link", { name: "How It Works" })).toHaveAttribute("aria-current", "page");
    expect(within(desktop).getByRole("link", { name: "Product" })).not.toHaveAttribute("aria-current");
  });

  it("opens and closes the mobile menu with the button and Escape", () => {
    render(<SiteNav />);
    const toggle = screen.getByRole("button", { name: "Open menu" });
    const menu = document.getElementById("mobile-nav")!;
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(menu).not.toBeVisible();

    fireEvent.click(toggle);
    expect(screen.getByRole("button", { name: "Close menu" })).toHaveAttribute("aria-expanded", "true");
    expect(menu).toBeVisible();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(screen.getByRole("button", { name: "Open menu" })).toHaveAttribute("aria-expanded", "false");
  });
});

describe("HomePage", () => {
  it("has one heading level 1 and the two primary actions", () => {
    render(<HomePage />);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
    expect(screen.getByRole("link", { name: "Try Playground" })).toHaveAttribute("href", "/playground");
    expect(screen.getByRole("link", { name: "Download" })).toHaveAttribute("href", "/download");
    expect(screen.getByText(/Not yet released/)).toBeInTheDocument();
  });
});

describe("truthful states", () => {
  it("the playground shows an empty state, not sample data", () => {
    render(<PlaygroundPage />);
    expect(screen.getByText("Coming soon")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "No recordings yet" })).toBeInTheDocument();
  });

  it("the footer marks support and social links as not set up", () => {
    render(<SiteFooter />);
    expect(screen.getByText("Not set up yet")).toBeInTheDocument();
    expect(screen.getByText("Placeholder")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Privacy" })).toHaveAttribute("href", "/privacy");
    expect(screen.getByRole("link", { name: "Terms" })).toHaveAttribute("href", "/terms");
    expect(screen.getByRole("link", { name: /GitHub/ })).toHaveAttribute("rel", "noreferrer");
  });
});

describe("Topology", () => {
  it("is an image with a text description and labelled as an illustration", () => {
    render(<Topology />);
    expect(
      screen.getByRole("img", { name: /Illustration of the sample shop application under a pod-delete/ }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Not recorded data/)).toBeInTheDocument();
  });
});
