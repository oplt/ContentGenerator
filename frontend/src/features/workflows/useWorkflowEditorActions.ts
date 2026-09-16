import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  publishWorkflowVersion,
  saveWorkflowDraft,
  startWorkflowRun,
  testWorkflowNode,
  validateWorkflowGraph,
  type DryRunOptions,
  type NodeTestResult,
  type WorkflowCompileError,
  type WorkflowGraph,
  type WorkflowGraphNode,
} from "../../api/workflows";
import { queryClient } from "../../lib/queryClient";
import { queryKeys } from "../../lib/queryKeys";

type Args = {
  definitionId: string;
  tenantId: string | null;
  graph: WorkflowGraph | null;
  selected: WorkflowGraphNode | null;
  compileContext: { social_account_ids: string[]; require_publish_targets: boolean };
  dryRunOptions: DryRunOptions;
  testInputs: string;
  setCompileErrors: (errors: WorkflowCompileError[]) => void;
  setMessage: (message: string | null) => void;
  setTestResult: (result: NodeTestResult | null) => void;
};

export function useWorkflowEditorActions({
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
}: Args) {
  const navigate = useNavigate();

  const invalidate = async () => {
    if (!tenantId) return;
    await queryClient.invalidateQueries({
      queryKey: queryKeys.workflowVersions(tenantId, definitionId),
    });
    await queryClient.invalidateQueries({
      queryKey: queryKeys.workflowDefinition(tenantId, definitionId),
    });
    await queryClient.invalidateQueries({ queryKey: queryKeys.workflowDefinitions(tenantId) });
  };

  const draftMutation = useMutation({
    mutationFn: () => {
      if (!graph) throw new Error("Graph not loaded");
      return saveWorkflowDraft(definitionId, { graph });
    },
    onSuccess: async (version) => {
      setMessage(`Draft saved (v${version.version})`);
      setCompileErrors([]);
      await invalidate();
    },
    onError: (error: Error) => setMessage(error.message),
  });

  const validateMutation = useMutation({
    mutationFn: async () => {
      if (!graph) throw new Error("Graph not loaded");
      await saveWorkflowDraft(definitionId, { graph });
      return validateWorkflowGraph({ graph, context: compileContext });
    },
    onSuccess: async (result) => {
      setCompileErrors(result.errors);
      setMessage(result.valid ? "Validate OK" : "Validate failed");
      await invalidate();
    },
    onError: (error: Error) => setMessage(error.message),
  });

  const publishMutation = useMutation({
    mutationFn: async () => {
      if (!graph) throw new Error("Graph not loaded");
      const draft = await saveWorkflowDraft(definitionId, { graph });
      const compiled = await validateWorkflowGraph({
        graph: draft.graph_json as WorkflowGraph,
        context: compileContext,
      });
      if (!compiled.valid) {
        setCompileErrors(compiled.errors);
        throw new Error("Validate failed — fix before publish");
      }
      return publishWorkflowVersion(definitionId, {
        version_id: draft.id,
        context: compileContext,
      });
    },
    onSuccess: async (version) => {
      setMessage(`Published v${version.version}`);
      setCompileErrors([]);
      await invalidate();
    },
    onError: (error: Error) => setMessage(error.message),
  });

  const runMutation = useMutation({
    mutationFn: () =>
      startWorkflowRun(definitionId, {
        context: compileContext,
        ...dryRunOptions,
      }),
    onSuccess: (detail) => navigate(`/dashboard/runs/${detail.run.id}`),
    onError: (error: Error) => setMessage(error.message),
  });

  const testNodeMutation = useMutation({
    mutationFn: async () => {
      if (!selected) throw new Error("Select a node");
      const inputs = JSON.parse(testInputs) as Record<string, unknown>;
      return testWorkflowNode(selected.type, {
        config: selected.config ?? {},
        inputs,
        dry_run: dryRunOptions.dry_run,
        mock_generation: dryRunOptions.mock_generation,
        context: compileContext,
      });
    },
    onSuccess: (result) => {
      setTestResult(result);
      setMessage(`Node test ${result.status}`);
    },
    onError: (error: Error) => setMessage(error.message),
  });

  const busy =
    draftMutation.isPending ||
    validateMutation.isPending ||
    publishMutation.isPending ||
    runMutation.isPending;

  return {
    busy,
    draftMutation,
    validateMutation,
    publishMutation,
    runMutation,
    testNodeMutation,
  };
}
