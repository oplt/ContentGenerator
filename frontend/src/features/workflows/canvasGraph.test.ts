import { describe, expect, it } from "vitest";
import {
  autoLayoutGraph,
  defaultEdgeCondition,
  flowToGraph,
  graphToFlow,
  readLayout,
  type WorkflowNodeData,
} from "./canvasGraph";
import { DEFAULT_LINEAR_GRAPH } from "../../api/workflows";
import type { Edge, Node } from "@xyflow/react";

describe("canvasGraph", () => {
  it("round-trips graph through flow adapters and keeps layout", () => {
    const withPos = autoLayoutGraph(DEFAULT_LINEAR_GRAPH);
    const { nodes, edges } = graphToFlow(withPos, { generate_text: "Generate Text" });
    expect(nodes).toHaveLength(4);
    expect(nodes[1]?.data.label).toBe("Generate Text");
    expect(edges[2]?.data?.condition).toBe("approved");

    const back = flowToGraph(nodes as Node<WorkflowNodeData>[], edges as Edge[], withPos.metadata);
    expect(back.nodes.map((n) => n.id)).toEqual(withPos.nodes.map((n) => n.id));
    expect(back.edges).toHaveLength(3);
    expect(readLayout(back).approval).toEqual(readLayout(withPos).approval);
  });

  it("defaults approval edge condition", () => {
    expect(defaultEdgeCondition("approval")).toBe("approved");
    expect(defaultEdgeCondition("generate_text")).toBeNull();
  });
});
