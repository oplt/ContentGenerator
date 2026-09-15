import { describe, expect, it } from "vitest";
import { isCanonicalStoryClusterId } from "./stories";

describe("story cluster identifiers", () => {
  it("accepts canonical UUIDs and rejects legacy ObjectId-shaped values", () => {
    expect(isCanonicalStoryClusterId("6aa967ea-b699-18de-8da3-73363b8d6d4a")).toBe(true);
    expect(isCanonicalStoryClusterId("6aa967eab69918de8da37363")).toBe(false);
  });
});
