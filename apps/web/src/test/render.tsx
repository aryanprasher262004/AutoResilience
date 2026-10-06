import { QueryClientProvider } from "@tanstack/react-query";
import { render } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactElement } from "react";
import { vi } from "vitest";

import { QUERY_DEFAULTS, createQueryClient } from "@/lib/api/query-client";

/** Renders with the console's real QueryClient defaults, minus retries (fast, deterministic). */
export function renderWithApi(ui: ReactElement) {
  const client = createQueryClient({ ...QUERY_DEFAULTS, queries: { ...QUERY_DEFAULTS.queries, retry: false } });
  // Lets user-event's own delays progress when a test uses fake timers.
  const user = userEvent.setup({
    advanceTimers: (ms) => {
      if (vi.isFakeTimers()) vi.advanceTimersByTime(ms);
    },
  });
  return { user, client, ...render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>) };
}
