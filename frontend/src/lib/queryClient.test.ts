import { queryClient } from "./queryClient";
import { shouldRetryQuery } from "./queryRetry";

describe("queryClient defaults", () => {
  it("uses shouldRetryQuery for queries and disables mutation retries", () => {
    const defaults = queryClient.getDefaultOptions();
    expect(defaults.queries?.retry).toBe(shouldRetryQuery);
    expect(defaults.mutations?.retry).toBe(false);
  });

  it("uses moderate staleTime to dedupe duplicate GETs within the window", () => {
    const staleTime = queryClient.getDefaultOptions().queries?.staleTime;
    expect(typeof staleTime).toBe("number");
    expect(staleTime).toBeGreaterThanOrEqual(60_000);
  });
});
