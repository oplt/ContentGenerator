import type { WorkflowGraph, WorkflowGraphNode } from "../../api/workflows";

export function orderedNodes(graph: WorkflowGraph): WorkflowGraphNode[] {
  const byId = new Map(graph.nodes.map((node) => [node.id, node]));
  const incoming = new Map<string, number>();
  for (const node of graph.nodes) incoming.set(node.id, 0);
  for (const edge of graph.edges) {
    incoming.set(edge.target, (incoming.get(edge.target) ?? 0) + 1);
  }
  const queue = graph.nodes
    .filter((node) => (incoming.get(node.id) ?? 0) === 0)
    .map((node) => node.id);
  const order: string[] = [];
  const adj = new Map<string, string[]>();
  for (const edge of graph.edges) {
    const list = adj.get(edge.source) ?? [];
    list.push(edge.target);
    adj.set(edge.source, list);
  }
  while (queue.length) {
    const id = queue.shift()!;
    order.push(id);
    for (const next of adj.get(id) ?? []) {
      const count = (incoming.get(next) ?? 1) - 1;
      incoming.set(next, count);
      if (count === 0) queue.push(next);
    }
  }
  for (const node of graph.nodes) {
    if (!order.includes(node.id)) order.push(node.id);
  }
  return order.map((id) => byId.get(id)!).filter(Boolean);
}

export function rebuildLinearEdges(nodes: WorkflowGraphNode[]): WorkflowGraph["edges"] {
  const edges: WorkflowGraph["edges"] = [];
  for (let i = 0; i < nodes.length - 1; i += 1) {
    const source = nodes[i];
    const target = nodes[i + 1];
    edges.push({
      source: source.id,
      target: target.id,
      condition: source.type === "approval" ? "approved" : null,
    });
  }
  return edges;
}
