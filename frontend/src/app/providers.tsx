import type { PropsWithChildren } from "react";
import { QueryClientProvider } from "@tanstack/react-query";
import { AuthProvider } from "../features/auth/AuthContext";
import { queryClient } from "../lib/queryClient";

export function AppProviders({ children }: PropsWithChildren) {
  return (
    <QueryClientProvider client={queryClient}>
      <AuthProvider>{children}</AuthProvider>
    </QueryClientProvider>
  );
}
