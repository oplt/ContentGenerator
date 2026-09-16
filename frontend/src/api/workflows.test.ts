import { describe, expect, it } from "vitest";
import { DEFAULT_LINEAR_GRAPH } from "./workflows";

describe("workflows api helpers", () => {
  it("ships a valid default linear graph", () => {
    expect(DEFAULT_LINEAR_GRAPH.nodes.map((n) => n.type)).toEqual([
      "manual_trigger",
      "generate_text",
      "approval",
      "publish",
    ]);
    expect(DEFAULT_LINEAR_GRAPH.edges).toHaveLength(3);
    expect(DEFAULT_LINEAR_GRAPH.edges[2]?.condition).toBe("approved");
  });
});
