import { QueryClient } from "@tanstack/react-query";

/** A React Query client for tests: no retries, no refetch on focus, nothing garbage-collected. */
export function testQueryClient(): QueryClient {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: Infinity, refetchOnWindowFocus: false },
      mutations: { retry: false },
    },
  });
}
