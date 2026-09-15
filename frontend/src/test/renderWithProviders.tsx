/* eslint-disable react-refresh/only-export-components -- test utility module */
import type { ReactElement, ReactNode } from "react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import * as Tooltip from "@radix-ui/react-tooltip";
import { render, type RenderOptions } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

export function createTestQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false },
      mutations: { retry: false },
    },
  });
}

type ProvidersProps = {
  children: ReactNode;
  queryClient?: QueryClient;
  initialEntries?: string[];
};

export function AllProviders({
  children,
  queryClient = createTestQueryClient(),
  initialEntries = ["/"],
}: ProvidersProps) {
  return (
    <QueryClientProvider client={queryClient}>
      <Tooltip.Provider delayDuration={200}>
        <MemoryRouter initialEntries={initialEntries}>{children}</MemoryRouter>
      </Tooltip.Provider>
    </QueryClientProvider>
  );
}

export function renderWithProviders(
  ui: ReactElement,
  options?: Omit<RenderOptions, "wrapper"> & {
    queryClient?: QueryClient;
    initialEntries?: string[];
  }
) {
  const { queryClient, initialEntries, ...renderOptions } = options ?? {};
  return render(ui, {
    wrapper: ({ children }) => (
      <AllProviders queryClient={queryClient} initialEntries={initialEntries}>
        {children}
      </AllProviders>
    ),
    ...renderOptions,
  });
}
