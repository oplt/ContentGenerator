import type { PropsWithChildren } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import * as Tooltip from "@radix-ui/react-tooltip";
import { AuthProvider } from "../features/auth/AuthContext";
import { queryClient } from "../lib/queryClient";

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider client={queryClient}>
      <Tooltip.Provider delayDuration={200}>
        <AuthProvider>{children}</AuthProvider>
      </Tooltip.Provider>
    </QueryClientProvider>
  );
}
