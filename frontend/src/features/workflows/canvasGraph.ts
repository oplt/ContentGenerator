/** WorkflowGraph <-> React Flow adapters. Layout lives in metadata.layout. */

import type { Edge, Node } from "@xyflow/react";
import type {
  WorkflowGraph,
  WorkflowGraphEdge,
  WorkflowGraphNode,
  WorkflowNodeDefinition,
  WorkflowNodePort,
} from "../../api/workflows";
import { orderedNodes } from "./editorGraph";
import { DEFAULT_HANDLE_ID } from "./portCompatibility";

export type WorkflowNodeData = {
  type: string;
  version: number;
  config: Record<string, unknown>;
  displayName?: string;
  label: string;
  category?: string;
  implementationStatus?: string;
  executable?: boolean;
  mayPause?: boolean;
  inputPorts: WorkflowNodePort[];
  outputPorts: WorkflowNodePort[];
  invalid?: boolean;
  unavailable?: boolean;
  runStatus?: string | null;
};

export type LayoutMap = Record<string, { x: number; y: number }>;

export type GraphToFlowOptions = {
  displayNames?: Record<string, string>;
  catalog?: WorkflowNodeDefinition[];
  invalidNodeIds?: Set<string> | string[];
  runStatuses?: Record<string, string | null | undefined>;
};

export const PALETTE_CATEGORIES: Array<{ key: string; label: string }> = [
  { key: "triggers", label: "Triggers" },
  { key: "sources", label: "Sources" },
  { key: "ai_content", label: "AI" },
  { key: "chess", label: "Chess" },
  { key: "media", label: "Media" },
  { key: "control", label: "Control" },
  { key: "human", label: "Human" },
  { key: "distribution", label: "Distribution" },
  { key: "analytics", label: "Analytics" },
];

export function categoryGlyph(category: string | undefined): string {
  switch (category) {
    case "triggers":
      return "▶";
    case "sources":
      return "◎";
    case "ai_content":
      return "✦";
    case "chess":
      return "♟";
    case "media":
      return "▣";
    case "control":
      return "⇄";
    case "human":
      return "✓";
    case "distribution":
      return "⇢";
    case "analytics":
      return "▦";
    default:
      return "•";
  }
}

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
  return { x: 80 + (index % 4) * 260, y: 80 + Math.floor(index / 4) * 140 };
}

function resolveOptions(
  opts?: Record<string, string> | GraphToFlowOptions,
): GraphToFlowOptions {
  if (!opts) return {};
  if (
    "catalog" in opts ||
    "displayNames" in opts ||
    "invalidNodeIds" in opts ||
    "runStatuses" in opts
  ) {
    return opts as GraphToFlowOptions;
  }
  return { displayNames: opts as Record<string, string> };
}

function toIdSet(value: Set<string> | string[] | undefined): Set<string> {
  if (!value) return new Set();
  return Array.isArray(value) ? new Set(value) : value;
}

function handleIdForPort(
  portName: string | null | undefined,
  ports: WorkflowNodePort[],
): string {
  if (portName && portName.length > 0) return portName;
  if (ports.length === 0) return DEFAULT_HANDLE_ID;
  // Legacy edges without ports: attach to the first declared port for display.
  return ports[0]!.name;
}

function portNameFromHandle(handleId: string | null | undefined): string | null {
  if (!handleId || handleId === DEFAULT_HANDLE_ID) return null;
  return handleId;
}

export function graphToFlow(
  graph: WorkflowGraph,
  displayNamesOrOptions?: Record<string, string> | GraphToFlowOptions,
): { nodes: Node<WorkflowNodeData>[]; edges: Edge[] } {
  const options = resolveOptions(displayNamesOrOptions);
  const byType = new Map((options.catalog ?? []).map((item) => [item.type, item]));
  const invalid = toIdSet(options.invalidNodeIds);
  const layout = readLayout(graph);

  const nodes: Node<WorkflowNodeData>[] = graph.nodes.map((node, index) => {
    const pos = layout[node.id] ?? defaultPosition(index);
    const def = byType.get(node.type);
    const label = options.displayNames?.[node.type] ?? def?.display_name ?? node.type;
    const unavailable =
      def?.executable === false || def?.implementation_status === "unavailable";
    return {
      id: node.id,
      type: "workflow",
      position: pos,
      data: {
        type: node.type,
        version: node.version,
        config: node.config ?? {},
        displayName: options.displayNames?.[node.type] ?? def?.display_name,
        label,
        category: def?.category,
        implementationStatus: def?.implementation_status,
        executable: def?.executable,
        mayPause: def?.may_pause,
        inputPorts: def?.input_ports ?? [],
        outputPorts: def?.output_ports ?? [],
        invalid: invalid.has(node.id),
        unavailable,
        runStatus: options.runStatuses?.[node.id] ?? null,
      },
    };
  });

  const defByNodeId = new Map(
    graph.nodes.map((node) => [node.id, byType.get(node.type)] as const),
  );
  const edges: Edge[] = graph.edges.map((edge, index) => {
    const sourcePorts = defByNodeId.get(edge.source)?.output_ports ?? [];
    const targetPorts = defByNodeId.get(edge.target)?.input_ports ?? [];
    const sourceHandle = handleIdForPort(edge.source_port, sourcePorts);
    const targetHandle = handleIdForPort(edge.target_port, targetPorts);
    return {
      id: `e-${edge.source}-${edge.target}-${sourceHandle}-${targetHandle}-${index}`,
      source: edge.source,
      target: edge.target,
      sourceHandle,
      targetHandle,
      label: edge.condition ?? undefined,
      data: {
        condition: edge.condition ?? null,
        source_port: edge.source_port ?? null,
        target_port: edge.target_port ?? null,
      },
    };
  });
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
  const graphEdges: WorkflowGraphEdge[] = edges.map((edge) => {
    const sourcePort =
      portNameFromHandle(edge.sourceHandle) ??
      ((edge.data?.source_port as string | null | undefined) ?? null);
    const targetPort =
      portNameFromHandle(edge.targetHandle) ??
      ((edge.data?.target_port as string | null | undefined) ?? null);
    return {
      source: edge.source,
      target: edge.target,
      condition: (edge.data?.condition as string | null | undefined) ?? null,
      source_port: sourcePort,
      target_port: targetPort,
    };
  });
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
    layout[node.id] = { x: 120, y: 80 + index * 160 };
  });
  return withLayout(graph, layout);
}

export function newNodeId(type: string): string {
  return `${type}_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 6)}`;
}

export function defaultEdgeCondition(sourceType: string): string | null {
  return sourceType === "approval" ? "approved" : null;
}
