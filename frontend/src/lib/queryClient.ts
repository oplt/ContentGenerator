import { QueryClient } from "@tanstack/react-query";
import { queryPolicy } from "./queryPolicy";
import { shouldRetryQuery } from "./queryRetry";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      ...queryPolicy.moderate,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
      retry: shouldRetryQuery,
    },
    mutations: {
      // Never auto-retry POST/PUT/PATCH/DELETE — including non-idempotent writes.
      retry: false,
    },
  },
});
