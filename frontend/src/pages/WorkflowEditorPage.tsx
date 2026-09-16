import { useEffect, useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  getWorkflowDefinition,
  listWorkflowNodes,
  listWorkflowVersions,
  type DryRunOptions,
  type NodeTestResult,
  type WorkflowCompileError,
  type WorkflowGraph,
  type WorkflowGraphNode,
} from "../api/workflows";
import { getSocialAccounts } from "../api/publishing";
import { useTenantScope } from "../hooks/useTenantScope";
import { useAccountSelection } from "../hooks/useAccountSelection";
import { queryKeys } from "../lib/queryKeys";
import { queryPolicy } from "../lib/queryPolicy";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { SocialAccountSelector } from "../components/dashboard/SocialAccountSelector";
import {
  WorkflowEditorActions,
  WorkflowStepConfigPanel,
} from "../features/workflows/WorkflowEditorPanels";
import { WorkflowValidationPanel } from "../features/workflows/WorkflowValidationPanel";
import { WorkflowCanvas } from "../features/workflows/WorkflowCanvas";
import { WorkflowNodePalette } from "../features/workflows/WorkflowNodePalette";
import { useWorkflowEditorActions } from "../features/workflows/useWorkflowEditorActions";
import {
  autoLayoutGraph,
  defaultPosition,
  newNodeId,
  readLayout,
  withLayout,
} from "../features/workflows/canvasGraph";
import { defaultConfigFromSchema } from "../features/workflows/schemaFields";

const DEFAULT_DRY_RUN: DryRunOptions = {
  dry_run: true,
  mock_generation: true,
  simulate_approval: true,
};

export default function WorkflowEditorPage() {
  const { definitionId = "" } = useParams();
  const { tenantId, enabled } = useTenantScope();
  const { selectedIds, setSelectedIds } = useAccountSelection(tenantId);
  const [graph, setGraph] = useState<WorkflowGraph | null>(null);
  const [selectedStepId, setSelectedStepId] = useState<string | null>(null);
  const [compileErrors, setCompileErrors] = useState<WorkflowCompileError[]>([]);
  const [message, setMessage] = useState<string | null>(null);
  const [dryRunOptions, setDryRunOptions] = useState<DryRunOptions>(DEFAULT_DRY_RUN);
  const [testInputs, setTestInputs] = useState("{}");
  const [testResult, setTestResult] = useState<NodeTestResult | null>(null);

  const definition = useQuery({
    queryKey: queryKeys.workflowDefinition(tenantId ?? "none", definitionId),
    queryFn: ({ signal }) => getWorkflowDefinition(definitionId, { signal }),
    enabled: enabled && Boolean(definitionId),
    ...queryPolicy.moderate,
  });
  const versions = useQuery({
    queryKey: queryKeys.workflowVersions(tenantId ?? "none", definitionId),
    queryFn: ({ signal }) => listWorkflowVersions(definitionId, { signal }),
    enabled: enabled && Boolean(definitionId),
    ...queryPolicy.moderate,
  });
  const catalog = useQuery({
    queryKey: queryKeys.workflowNodes(tenantId ?? "none"),
    queryFn: ({ signal }) => listWorkflowNodes({ signal }),
    enabled,
    ...queryPolicy.static,
  });
  const accounts = useQuery({
    queryKey: queryKeys.socialAccounts(tenantId ?? "none"),
    queryFn: getSocialAccounts,
    enabled,
    ...queryPolicy.moderate,
  });

  const latest = versions.data?.[0] ?? null;
  useEffect(() => {
    if (latest && !graph) {
      // Seed local editable state once after the remote version arrives.
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setGraph(structuredClone(latest.graph_json) as WorkflowGraph);
      setSelectedStepId(latest.graph_json.nodes[0]?.id ?? null);
    }
  }, [latest, graph]);

  const selected = graph?.nodes.find((node) => node.id === selectedStepId) ?? null;
  const selectedDefinition =
    catalog.data?.find((item) => item.type === selected?.type) ?? null;
  const displayNames = useMemo(
    () => Object.fromEntries((catalog.data ?? []).map((n) => [n.type, n.display_name])),
    [catalog.data],
  );
  const invalidNodeIds = useMemo(
    () =>
      compileErrors
        .map((error) => error.node_id)
        .filter((id): id is string => Boolean(id)),
    [compileErrors],
  );
  const compileContext = {
    social_account_ids: selectedIds,
    require_publish_targets: selectedIds.length > 0,
  };

  const actions = useWorkflowEditorActions({
    definitionId,
    tenantId,
    graph,
    selected,
    compileContext,
    dryRunOptions,
    testInputs,
    setCompileErrors,
    setMessage,
    setTestResult,
  });

  function updateSelectedConfig(nextConfig: Record<string, unknown>) {
    if (!graph || !selected) return;
    setGraph({
      ...graph,
      nodes: graph.nodes.map((node) =>
        node.id === selected.id ? { ...node, config: nextConfig } : node,
      ),
    });
  }

  function addNode(nodeType: string) {
    if (!graph) return;
    const def = catalog.data?.find((item) => item.type === nodeType);
    const id = newNodeId(nodeType);
    const node: WorkflowGraphNode = {
      id,
      type: nodeType,
      version: def?.version ?? 1,
      config: defaultConfigFromSchema(def?.config_schema),
    };
    const layout = { ...readLayout(graph), [id]: defaultPosition(graph.nodes.length) };
    setGraph(withLayout({ ...graph, nodes: [...graph.nodes, node] }, layout));
    setSelectedStepId(id);
  }

  function duplicateSelected() {
    if (!graph || !selected) return;
    const id = newNodeId(selected.type);
    const layout = readLayout(graph);
    const prev = layout[selected.id] ?? defaultPosition(0);
    const clone: WorkflowGraphNode = {
      ...selected,
      id,
      config: structuredClone(selected.config ?? {}),
    };
    setGraph(
      withLayout(
        { ...graph, nodes: [...graph.nodes, clone] },
        { ...layout, [id]: { x: prev.x + 40, y: prev.y + 40 } },
      ),
    );
    setSelectedStepId(id);
  }

  if (definition.isLoading || versions.isLoading) {
    return <LoadingState label="Loading workflow editor" />;
  }
  if (definition.isError || !definition.data) {
    return <ErrorState title="Workflow not found" message="It may have been deleted." />;
  }

  return (
    <div className="space-y-4">
      <Card className="p-5">
        <Button asChild variant="ghost" size="sm" className="mb-2 px-0">
          <Link to="/dashboard/workflows">Back</Link>
        </Button>
        <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
          <div>
            <h1 className="text-2xl font-semibold">{definition.data.name}</h1>
            <p className="mt-1 text-sm text-muted-foreground">
              Port-based canvas + schema-driven node config (Phase 14).
            </p>
          </div>
          <WorkflowEditorActions
            busy={actions.busy}
            hasGraph={Boolean(graph)}
            dryRunOptions={dryRunOptions}
            onDryRunOptionsChange={setDryRunOptions}
            onDraft={() => actions.draftMutation.mutate()}
            onValidate={() => actions.validateMutation.mutate()}
            onPublish={() => actions.publishMutation.mutate()}
            onTestRun={() => actions.runMutation.mutate()}
          />
        </div>
        {message ? <p className="mt-2 text-sm text-muted-foreground">{message}</p> : null}
      </Card>

      <Card className="p-4">
        <SocialAccountSelector
          accounts={accounts.data ?? []}
          selectedIds={selectedIds}
          onChange={setSelectedIds}
          label="Publish targets"
        />
      </Card>

      <div className="grid gap-4 lg:grid-cols-[200px_minmax(0,1fr)_300px]">
        <Card className="max-h-[640px] overflow-hidden p-3">
          <h2 className="mb-3 text-sm font-semibold">Palette</h2>
          <WorkflowNodePalette catalog={catalog.data ?? []} onAdd={addNode} />
        </Card>
        <Card className="h-[640px] p-3">
          {graph ? (
            <WorkflowCanvas
              graph={graph}
              displayNames={displayNames}
              catalog={catalog.data ?? []}
              invalidNodeIds={invalidNodeIds}
              selectedNodeId={selectedStepId}
              onGraphChange={setGraph}
              onSelectNode={setSelectedStepId}
              onAutoLayout={() =>
                setGraph((current) => (current ? autoLayoutGraph(current) : current))
              }
              onDuplicate={duplicateSelected}
            />
          ) : (
            <p className="text-sm text-muted-foreground">Loading graph…</p>
          )}
        </Card>
        <Card className="space-y-3 p-4">
          <h2 className="text-sm font-semibold">Node config</h2>
          <WorkflowStepConfigPanel
            selected={selected}
            definition={selectedDefinition}
            onConfigChange={updateSelectedConfig}
            testInputs={testInputs}
            onTestInputsChange={setTestInputs}
            onTestNode={() => actions.testNodeMutation.mutate()}
            testBusy={actions.testNodeMutation.isPending}
            testResult={testResult}
          />
        </Card>
      </div>

      <Card className="p-4">
        <h2 className="text-sm font-semibold">Validation</h2>
        <WorkflowValidationPanel errors={compileErrors} />
      </Card>
    </div>
  );
}
