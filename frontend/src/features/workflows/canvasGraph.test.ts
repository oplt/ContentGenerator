import { describe, expect, it } from "vitest";
import type { Edge, Node } from "@xyflow/react";
import { DEFAULT_LINEAR_GRAPH, type WorkflowNodeDefinition } from "../../api/workflows";
import {
  autoLayoutGraph,
  defaultEdgeCondition,
  flowToGraph,
  graphToFlow,
  readLayout,
  type WorkflowNodeData,
} from "./canvasGraph";
import { DEFAULT_HANDLE_ID, portsCompatible, typesCompatible } from "./portCompatibility";

const generateTextDef: WorkflowNodeDefinition = {
  type: "generate_text",
  version: 1,
  category: "ai_content",
  display_name: "Generate Text",
  description: "test",
  implementation_status: "stable",
  executable: true,
  config_schema: {},
  input_ports: [
    { name: "prompt", data_type: "string" },
    { name: "system_hint", data_type: "string", required: false },
  ],
  output_ports: [
    { name: "text", data_type: "string" },
    { name: "provider", data_type: "string" },
  ],
  required_capabilities: ["llm"],
  may_pause: false,
};

const approvalDef: WorkflowNodeDefinition = {
  type: "approval",
  version: 1,
  category: "human",
  display_name: "Approval",
  description: "test",
  implementation_status: "stable",
  executable: true,
  config_schema: {},
  input_ports: [{ name: "content_job_id", data_type: "uuid" }],
  output_ports: [
    { name: "decision", data_type: "string" },
    { name: "content_job_id", data_type: "uuid" },
  ],
  required_capabilities: [],
  may_pause: true,
};

const stubDef: WorkflowNodeDefinition = {
  type: "research_sources",
  version: 1,
  category: "sources",
  display_name: "Research Sources",
  description: "stub",
  implementation_status: "unavailable",
  executable: false,
  config_schema: {},
  input_ports: [],
  output_ports: [],
  required_capabilities: [],
  may_pause: false,
};

describe("portCompatibility", () => {
  it("mirrors backend soft coercions", () => {
    expect(typesCompatible("string", "uuid")).toBe(true);
    expect(typesCompatible("text", "string")).toBe(true);
    expect(typesCompatible("number", "string")).toBe(false);
    expect(portsCompatible({ name: "a", data_type: "string" }, { name: "b", data_type: "uuid" })).toBe(
      true,
    );
    expect(portsCompatible(null, { name: "b", data_type: "string" })).toBe(true);
  });
});

describe("canvasGraph ports", () => {
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

  it("serializes sourceHandle/targetHandle into GraphEdge ports", () => {
    const graph = {
      nodes: [
        { id: "gen", type: "generate_text", version: 1, config: {} },
        { id: "appr", type: "approval", version: 1, config: {} },
      ],
      edges: [
        {
          source: "gen",
          target: "appr",
          source_port: "text",
          target_port: "content_job_id",
          condition: null,
        },
      ],
      metadata: {},
    };
    const { nodes, edges } = graphToFlow(graph, {
      catalog: [generateTextDef, approvalDef],
    });
    expect(edges[0]?.sourceHandle).toBe("text");
    expect(edges[0]?.targetHandle).toBe("content_job_id");
    expect(nodes[0]?.data.outputPorts.map((p) => p.name)).toEqual(["text", "provider"]);
    expect(nodes[1]?.data.mayPause).toBe(true);

    const back = flowToGraph(nodes as Node<WorkflowNodeData>[], edges as Edge[]);
    expect(back.edges[0]).toMatchObject({
      source: "gen",
      target: "appr",
      source_port: "text",
      target_port: "content_job_id",
    });
  });

  it("uses default handles when ports are omitted and catalog unknown", () => {
    const { edges } = graphToFlow(DEFAULT_LINEAR_GRAPH, {});
    expect(edges[0]?.sourceHandle).toBe(DEFAULT_HANDLE_ID);
    expect(edges[0]?.targetHandle).toBe(DEFAULT_HANDLE_ID);
    const back = flowToGraph(
      graphToFlow(DEFAULT_LINEAR_GRAPH).nodes as Node<WorkflowNodeData>[],
      edges as Edge[],
    );
    expect(back.edges[0]?.source_port).toBeNull();
    expect(back.edges[0]?.target_port).toBeNull();
  });

  it("maps legacy edges without ports onto first catalog port", () => {
    const graph = {
      nodes: [
        { id: "gen", type: "generate_text", version: 1, config: {} },
        { id: "appr", type: "approval", version: 1, config: {} },
      ],
      edges: [{ source: "gen", target: "appr" }],
      metadata: {},
    };
    const { edges } = graphToFlow(graph, { catalog: [generateTextDef, approvalDef] });
    expect(edges[0]?.sourceHandle).toBe("text");
    expect(edges[0]?.targetHandle).toBe("content_job_id");
  });

  it("marks invalid and unavailable nodes from options/catalog", () => {
    const graph = {
      nodes: [
        { id: "a", type: "generate_text", version: 1, config: {} },
        { id: "b", type: "research_sources", version: 1, config: {} },
      ],
      edges: [],
      metadata: {},
    };
    const { nodes } = graphToFlow(graph, {
      catalog: [generateTextDef, stubDef],
      invalidNodeIds: ["a"],
      runStatuses: { a: "WAITING" },
    });
    expect(nodes[0]?.data.invalid).toBe(true);
    expect(nodes[0]?.data.runStatus).toBe("WAITING");
    expect(nodes[0]?.data.unavailable).toBe(false);
    expect(nodes[1]?.data.unavailable).toBe(true);
  });

  it("defaults approval edge condition", () => {
    expect(defaultEdgeCondition("approval")).toBe("approved");
    expect(defaultEdgeCondition("generate_text")).toBeNull();
  });
});
