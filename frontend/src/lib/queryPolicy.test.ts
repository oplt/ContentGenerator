import { describe, expect, it } from "vitest";
import { queryPolicy } from "./queryPolicy";

describe("queryPolicy", () => {
  it("keeps static data fresher longer than fast job data", () => {
    expect(queryPolicy.static.staleTime).toBeGreaterThan(queryPolicy.moderate.staleTime);
    expect(queryPolicy.moderate.staleTime).toBeGreaterThan(queryPolicy.fast.staleTime);
    expect(queryPolicy.health.staleTime).toBeGreaterThan(queryPolicy.fast.staleTime);
  });
});
