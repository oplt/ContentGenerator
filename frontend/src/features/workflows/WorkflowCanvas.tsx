import { useCallback, useEffect, useMemo, useRef } from "react";
import {
  Background,
  Controls,
  MiniMap,
  ReactFlow,
  ReactFlowProvider,
  addEdge,
  useEdgesState,
  useNodesState,
  useReactFlow,
  type Connection,
  type Edge,
  type Node,
  type OnSelectionChangeParams,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { WorkflowGraph } from "../../api/workflows";
import { Button } from "../../components/ui/button";
import { WorkflowCanvasNode } from "./WorkflowCanvasNode";
import {
  defaultEdgeCondition,
  flowToGraph,
  graphToFlow,
  type WorkflowNodeData,
} from "./canvasGraph";

const nodeTypes = { workflow: WorkflowCanvasNode };

type Props = {
  graph: WorkflowGraph;
  displayNames: Record<string, string>;
  selectedNodeId: string | null;
  onGraphChange: (graph: WorkflowGraph) => void;
  onSelectNode: (nodeId: string | null) => void;
  onAutoLayout: () => void;
  onDuplicate: () => void;
};

function CanvasInner({
  graph,
  displayNames,
  selectedNodeId,
  onGraphChange,
  onSelectNode,
  onAutoLayout,
  onDuplicate,
}: Props) {
  const seed = useMemo(() => graphToFlow(graph, displayNames), [graph, displayNames]);
  const [nodes, setNodes, onNodesChange] = useNodesState(seed.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(seed.edges);
  const { fitView, getNodes, getEdges } = useReactFlow<Node<WorkflowNodeData>>();
  const skipSync = useRef(false);
  const metaRef = useRef(graph.metadata);
  metaRef.current = graph.metadata;

  useEffect(() => {
    if (skipSync.current) {
      skipSync.current = false;
      return;
    }
    const next = graphToFlow(graph, displayNames);
    setNodes(next.nodes);
    setEdges(next.edges);
  }, [graph, displayNames, setNodes, setEdges]);

  useEffect(() => {
    setNodes((current) =>
      current.map((node) => ({ ...node, selected: node.id === selectedNodeId })),
    );
  }, [selectedNodeId, setNodes]);

  const pushGraph = useCallback(
    (nextNodes: Node<WorkflowNodeData>[], nextEdges: Edge[]) => {
      skipSync.current = true;
      onGraphChange(flowToGraph(nextNodes, nextEdges, metaRef.current));
    },
    [onGraphChange],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      const source = nodes.find((node) => node.id === connection.source);
      const condition = defaultEdgeCondition(source?.data.type ?? "");
      setEdges((current) => {
        const next = addEdge(
          { ...connection, data: { condition }, label: condition ?? undefined },
          current,
        );
        pushGraph(nodes, next);
        return next;
      });
    },
    [nodes, pushGraph, setEdges],
  );

  const onNodeDragStop = useCallback(() => {
    pushGraph(getNodes() as Node<WorkflowNodeData>[], getEdges());
  }, [getEdges, getNodes, pushGraph]);

  const onSelectionChange = useCallback(
    ({ nodes: selected }: OnSelectionChangeParams) => {
      onSelectNode(selected[0]?.id ?? null);
    },
    [onSelectNode],
  );

  const onEdgesDelete = useCallback(
    (deleted: Edge[]) => {
      const ids = new Set(deleted.map((edge) => edge.id));
      pushGraph(
        nodes,
        edges.filter((edge) => !ids.has(edge.id)),
      );
    },
    [edges, nodes, pushGraph],
  );

  const onNodesDelete = useCallback(
    (deleted: Node[]) => {
      const ids = new Set(deleted.map((node) => node.id));
      pushGraph(
        nodes.filter((node) => !ids.has(node.id)),
        edges.filter((edge) => !ids.has(edge.source) && !ids.has(edge.target)),
      );
      onSelectNode(null);
    },
    [edges, nodes, onSelectNode, pushGraph],
  );

  return (
    <div className="flex h-full min-h-[420px] flex-col">
      <div className="mb-2 flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" onClick={onAutoLayout}>
          Auto-layout
        </Button>
        <Button size="sm" variant="secondary" disabled={!selectedNodeId} onClick={onDuplicate}>
          Duplicate
        </Button>
        <Button size="sm" variant="ghost" onClick={() => fitView({ padding: 0.2 })}>
          Fit
        </Button>
      </div>
      <div className="min-h-0 flex-1 rounded border border-border bg-[#F4F4F4]">
        <ReactFlow
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          onConnect={onConnect}
          onNodeDragStop={onNodeDragStop}
          onSelectionChange={onSelectionChange}
          onNodesDelete={onNodesDelete}
          onEdgesDelete={onEdgesDelete}
          fitView
          deleteKeyCode={["Backspace", "Delete"]}
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={16} size={1} />
          <Controls />
          <MiniMap pannable zoomable />
        </ReactFlow>
      </div>
    </div>
  );
}

export function WorkflowCanvas(props: Props) {
  return (
    <ReactFlowProvider>
      <CanvasInner {...props} />
    </ReactFlowProvider>
  );
}
