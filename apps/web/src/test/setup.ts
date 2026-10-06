import "@testing-library/jest-dom/vitest";

import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

import { assertNoUnhandledRequests } from "./api";
import { resetNavigation } from "./navigation";

vi.mock("next/navigation", () => import("./navigation"));
vi.mock("next/link", async () => ({ default: (await import("./navigation")).Link }));

afterEach(() => {
  cleanup();
  resetNavigation();
  vi.useRealTimers();
  assertNoUnhandledRequests();
});
