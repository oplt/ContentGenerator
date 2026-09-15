import { QueryClient } from "@tanstack/react-query";
import { queryPolicy } from "./queryPolicy";

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      ...queryPolicy.moderate,
      refetchOnWindowFocus: false,
      refetchOnReconnect: true,
      retry: (failureCount, error) => {
        if (error instanceof Error && "retryable" in error && (error as { retryable?: boolean }).retryable === false) {
          return false;
        }
        return failureCount < 1;
      },
    },
    mutations: {
      retry: false,
    },
  },
});
