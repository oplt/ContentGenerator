/** WorkflowGraph <-> React Flow adapters (Phase 14). Layout lives in metadata.layout. */

import type { Edge, Node } from "@xyflow/react";
import type { WorkflowGraph, WorkflowGraphEdge, WorkflowGraphNode } from "../../api/workflows";
import { orderedNodes } from "./editorGraph";

export type WorkflowNodeData = {
  type: string;
  version: number;
  config: Record<string, unknown>;
  displayName?: string;
  label: string;
};

export type LayoutMap = Record<string, { x: number; y: number }>;

export const PALETTE_CATEGORIES: Array<{ key: string; label: string }> = [
  { key: "triggers", label: "Triggers" },
  { key: "sources", label: "Sources" },
  { key: "ai_content", label: "AI" },
  { key: "media", label: "Media" },
  { key: "control", label: "Control" },
  { key: "human", label: "Human" },
  { key: "distribution", label: "Distribution" },
  { key: "analytics", label: "Analytics" },
];

export function readLayout(graph: WorkflowGraph): LayoutMap {
  const raw = graph.metadata?.layout;
  if (!raw || typeof raw !== "object") return {};
  return raw as LayoutMap;
}

export function withLayout(graph: WorkflowGraph, layout: LayoutMap): WorkflowGraph {
  return {
    ...graph,
    metadata: { ...(graph.metadata ?? {}), layout },
  };
}

export function defaultPosition(index: number): { x: number; y: number } {
  return { x: 80 + (index % 4) * 220, y: 80 + Math.floor(index / 4) * 120 };
}

export function graphToFlow(
  graph: WorkflowGraph,
  displayNames?: Record<string, string>,
): { nodes: Node<WorkflowNodeData>[]; edges: Edge[] } {
  const layout = readLayout(graph);
  const nodes: Node<WorkflowNodeData>[] = graph.nodes.map((node, index) => {
    const pos = layout[node.id] ?? defaultPosition(index);
    const label = displayNames?.[node.type] ?? node.type;
    return {
      id: node.id,
      type: "workflow",
      position: pos,
      data: {
        type: node.type,
        version: node.version,
        config: node.config ?? {},
        displayName: displayNames?.[node.type],
        label,
      },
    };
  });
  const edges: Edge[] = graph.edges.map((edge, index) => ({
    id: `e-${edge.source}-${edge.target}-${index}`,
    source: edge.source,
    target: edge.target,
    label: edge.condition ?? undefined,
    data: { condition: edge.condition ?? null },
  }));
  return { nodes, edges };
}

export function flowToGraph(
  nodes: Node<WorkflowNodeData>[],
  edges: Edge[],
  prevMetadata?: Record<string, unknown>,
): WorkflowGraph {
  const layout: LayoutMap = {};
  const graphNodes: WorkflowGraphNode[] = nodes.map((node) => {
    layout[node.id] = { x: node.position.x, y: node.position.y };
    return {
      id: node.id,
      type: node.data.type,
      version: node.data.version,
      config: node.data.config ?? {},
    };
  });
  const graphEdges: WorkflowGraphEdge[] = edges.map((edge) => ({
    source: edge.source,
    target: edge.target,
    condition: (edge.data?.condition as string | null | undefined) ?? null,
  }));
  return {
    nodes: graphNodes,
    edges: graphEdges,
    metadata: { ...(prevMetadata ?? {}), layout },
  };
}

export function autoLayoutGraph(graph: WorkflowGraph): WorkflowGraph {
  const ordered = orderedNodes(graph);
  const layout: LayoutMap = {};
  ordered.forEach((node, index) => {
    layout[node.id] = { x: 120, y: 80 + index * 120 };
  });
  return withLayout(graph, layout);
}

export function newNodeId(type: string): string {
  return `${type}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`;
}

export function defaultEdgeCondition(sourceType: string): string | null {
  return sourceType === "approval" ? "approved" : null;
}
