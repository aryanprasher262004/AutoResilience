import { type DefaultOptions, QueryClient } from "@tanstack/react-query";

/** The console's TanStack Query defaults (also used by the test suite). */
export const QUERY_DEFAULTS: DefaultOptions = {
  queries: { staleTime: 5_000, retry: 1, refetchOnWindowFocus: true },
};

export function createQueryClient(defaultOptions: DefaultOptions = QUERY_DEFAULTS): QueryClient {
  return new QueryClient({ defaultOptions });
}
