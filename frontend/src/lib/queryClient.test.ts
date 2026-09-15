import { queryClient } from "./queryClient";

describe("queryClient defaults", () => {
  it("uses bounded caching and conservative refetch defaults", () => {
    const defaults = queryClient.getDefaultOptions();

    expect(defaults.queries?.staleTime).toBe(5 * 60_000);
    expect(defaults.queries?.gcTime).toBe(30 * 60_000);
    expect(defaults.queries?.refetchOnWindowFocus).toBe(false);
    expect(defaults.queries?.refetchOnReconnect).toBe(true);
    expect(defaults.mutations?.retry).toBe(false);
  });
});
