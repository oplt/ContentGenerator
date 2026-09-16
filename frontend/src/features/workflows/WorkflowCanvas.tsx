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
import type { WorkflowGraph, WorkflowNodeDefinition } from "../../api/workflows";
import { Button } from "../../components/ui/button";
import { WorkflowCanvasNode } from "./WorkflowCanvasNode";
import {
  defaultEdgeCondition,
  flowToGraph,
  graphToFlow,
  type WorkflowNodeData,
} from "./canvasGraph";
import { DEFAULT_HANDLE_ID, findPort, portsCompatible } from "./portCompatibility";

const nodeTypes = { workflow: WorkflowCanvasNode };

type Props = {
  graph: WorkflowGraph;
  displayNames: Record<string, string>;
  catalog?: WorkflowNodeDefinition[];
  invalidNodeIds?: string[];
  runStatuses?: Record<string, string | null | undefined>;
  selectedNodeId: string | null;
  onGraphChange: (graph: WorkflowGraph) => void;
  onSelectNode: (nodeId: string | null) => void;
  onAutoLayout: () => void;
  onDuplicate: () => void;
};

function CanvasInner({
  graph,
  displayNames,
  catalog,
  invalidNodeIds,
  runStatuses,
  selectedNodeId,
  onGraphChange,
  onSelectNode,
  onAutoLayout,
  onDuplicate,
}: Props) {
  const flowOptions = useMemo(
    () => ({ displayNames, catalog, invalidNodeIds, runStatuses }),
    [catalog, displayNames, invalidNodeIds, runStatuses],
  );
  const seed = useMemo(() => graphToFlow(graph, flowOptions), [graph, flowOptions]);
  const [nodes, setNodes, onNodesChange] = useNodesState(seed.nodes);
  const [edges, setEdges, onEdgesChange] = useEdgesState(seed.edges);
  const { fitView, getNodes, getEdges } = useReactFlow<Node<WorkflowNodeData>>();
  const skipSync = useRef(false);
  const metaRef = useRef(graph.metadata);

  useEffect(() => {
    metaRef.current = graph.metadata;
  }, [graph.metadata]);

  useEffect(() => {
    if (skipSync.current) {
      skipSync.current = false;
      return;
    }
    const next = graphToFlow(graph, flowOptions);
    setNodes(next.nodes);
    setEdges(next.edges);
  }, [flowOptions, graph, setEdges, setNodes]);

  useEffect(() => {
    setNodes((current) =>
      current.map((node) => ({ ...node, selected: node.id === selectedNodeId })),
    );
  }, [selectedNodeId, setNodes]);

  useEffect(() => {
    function onKeyDown(event: KeyboardEvent) {
      const target = event.target as HTMLElement | null;
      if (target && (target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable)) {
        return;
      }
      if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "d") {
        event.preventDefault();
        if (selectedNodeId) onDuplicate();
      }
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onDuplicate, selectedNodeId]);

  const pushGraph = useCallback(
    (nextNodes: Node<WorkflowNodeData>[], nextEdges: Edge[]) => {
      skipSync.current = true;
      onGraphChange(flowToGraph(nextNodes, nextEdges, metaRef.current));
    },
    [onGraphChange],
  );

  const isValidConnection = useCallback(
    (connection: Connection | Edge) => {
      if (!connection.source || !connection.target) return false;
      if (connection.source === connection.target) return false;
      const sourceNode = nodes.find((node) => node.id === connection.source);
      const targetNode = nodes.find((node) => node.id === connection.target);
      if (!sourceNode || !targetNode) return false;
      if (sourceNode.data.unavailable || targetNode.data.unavailable) return false;
      const sourcePort = findPort(sourceNode.data.outputPorts, connection.sourceHandle);
      const targetPort = findPort(targetNode.data.inputPorts, connection.targetHandle);
      return portsCompatible(sourcePort, targetPort);
    },
    [nodes],
  );

  const onConnect = useCallback(
    (connection: Connection) => {
      if (!isValidConnection(connection)) return;
      const source = nodes.find((node) => node.id === connection.source);
      const condition = defaultEdgeCondition(source?.data.type ?? "");
      const sourcePort =
        connection.sourceHandle && connection.sourceHandle !== DEFAULT_HANDLE_ID
          ? connection.sourceHandle
          : null;
      const targetPort =
        connection.targetHandle && connection.targetHandle !== DEFAULT_HANDLE_ID
          ? connection.targetHandle
          : null;
      setEdges((current) => {
        const next = addEdge(
          {
            ...connection,
            data: { condition, source_port: sourcePort, target_port: targetPort },
            label: condition ?? undefined,
          },
          current,
        );
        pushGraph(nodes, next);
        return next;
      });
    },
    [isValidConnection, nodes, pushGraph, setEdges],
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
          isValidConnection={isValidConnection}
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
