import { describe, expect, it } from "vitest";
import { DEFAULT_LINEAR_GRAPH } from "../../api/workflows";
import { orderedNodes, rebuildLinearEdges } from "./editorGraph";

describe("editorGraph", () => {
  it("orders nodes in topological sequence", () => {
    const ordered = orderedNodes(DEFAULT_LINEAR_GRAPH);
    expect(ordered.map((node) => node.id)).toEqual([
      "trigger",
      "generate",
      "approval",
      "publish",
    ]);
  });

  it("rebuilds linear edges with approval condition", () => {
    const nodes = orderedNodes(DEFAULT_LINEAR_GRAPH);
    const edges = rebuildLinearEdges(nodes);
    expect(edges).toHaveLength(3);
    expect(edges[2]?.condition).toBe("approved");
    expect(edges[0]?.condition).toBeNull();
  });
});
