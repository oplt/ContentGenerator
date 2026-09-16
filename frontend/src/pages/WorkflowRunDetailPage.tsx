import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  advanceWorkflowRun,
  cancelWorkflowRun,
  getWorkflowRun,
  resumeWorkflowNode,
  retryWorkflowFromNode,
  retryWorkflowNode,
} from "../api/workflows";
import { useTenantScope } from "../hooks/useTenantScope";
import { useDocumentVisible } from "../hooks/useDocumentVisible";
import { queryClient } from "../lib/queryClient";
import { queryKeys } from "../lib/queryKeys";
import { queryPolicy } from "../lib/queryPolicy";
import { statusAwareRefetchInterval, workflowRunNeedsPolling } from "../lib/polling";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { WorkflowRunNodeCard } from "../features/workflows/WorkflowRunNodeCard";

export default function WorkflowRunDetailPage() {
  const { runId = "" } = useParams();
  const { tenantId, enabled } = useTenantScope();
  const visible = useDocumentVisible();

  const detail = useQuery({
    queryKey: queryKeys.workflowRun(tenantId ?? "none", runId),
    queryFn: ({ signal }) => getWorkflowRun(runId, { signal }),
    enabled: enabled && Boolean(runId),
    ...queryPolicy.fast,
    refetchInterval: visible
      ? statusAwareRefetchInterval(5_000, workflowRunNeedsPolling)
      : false,
  });

  const invalidate = async () => {
    if (!tenantId) return;
    await queryClient.invalidateQueries({ queryKey: queryKeys.workflowRun(tenantId, runId) });
    await queryClient.invalidateQueries({ queryKey: queryKeys.workflowRuns(tenantId) });
  };

  const advanceMutation = useMutation({
    mutationFn: () => advanceWorkflowRun(runId),
    onSuccess: invalidate,
  });
  const cancelMutation = useMutation({
    mutationFn: () => cancelWorkflowRun(runId),
    onSuccess: invalidate,
  });
  const retryMutation = useMutation({
    mutationFn: (nodeId: string) => retryWorkflowNode(runId, nodeId),
    onSuccess: invalidate,
  });
  const retryFromMutation = useMutation({
    mutationFn: (nodeId: string) => retryWorkflowFromNode(runId, nodeId),
    onSuccess: invalidate,
  });
  const resumeMutation = useMutation({
    mutationFn: (payload: { nodeId: string; outcome: string }) =>
      resumeWorkflowNode(runId, payload.nodeId, { outcome: payload.outcome }),
    onSuccess: invalidate,
  });

  if (detail.isLoading) return <LoadingState label="Loading run" />;
  if (detail.isError || !detail.data) {
    return <ErrorState title="Run not found" message="It may have been deleted." />;
  }

  const { run, nodes, meta } = detail.data;
  const busy =
    advanceMutation.isPending ||
    cancelMutation.isPending ||
    retryMutation.isPending ||
    retryFromMutation.isPending ||
    resumeMutation.isPending;
  const canCancel = ["queued", "running", "waiting", "failed"].includes(run.status);

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <Button asChild variant="ghost" size="sm" className="mb-2 px-0">
          <Link to="/dashboard/runs">Back to runs</Link>
        </Button>
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Run {run.id.slice(0, 8)}</h1>
            <dl className="mt-3 grid gap-1 text-sm text-muted-foreground sm:grid-cols-2">
              <div>
                <dt className="inline font-medium text-foreground">Status: </dt>
                <dd className="inline">{run.status}</dd>
              </div>
              <div>
                <dt className="inline font-medium text-foreground">Trigger: </dt>
                <dd className="inline">{run.trigger_type}</dd>
              </div>
              <div>
                <dt className="inline font-medium text-foreground">Automation: </dt>
                <dd className="inline">
                  {meta?.automation_name ?? run.automation_id?.slice(0, 8) ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="inline font-medium text-foreground">Brand: </dt>
                <dd className="inline">
                  {meta?.brand_name ?? run.brand_id?.slice(0, 8) ?? "—"}
                </dd>
              </div>
              <div>
                <dt className="inline font-medium text-foreground">Version: </dt>
                <dd className="inline">
                  {meta?.version_number != null
                    ? `v${meta.version_number}`
                    : run.workflow_version_id.slice(0, 8)}
                </dd>
              </div>
              <div>
                <dt className="inline font-medium text-foreground">Correlation: </dt>
                <dd className="inline break-all">{run.correlation_id ?? "—"}</dd>
              </div>
              <div>
                <dt className="inline font-medium text-foreground">Started: </dt>
                <dd className="inline">{run.started_at ?? "—"}</dd>
              </div>
              <div>
                <dt className="inline font-medium text-foreground">Finished: </dt>
                <dd className="inline">{run.finished_at ?? "—"}</dd>
              </div>
            </dl>
            {run.error_message ? (
              <p className="mt-2 text-sm text-destructive">{run.error_message}</p>
            ) : null}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={busy}
              onClick={() => advanceMutation.mutate()}
            >
              Advance
            </Button>
            {canCancel ? (
              <Button
                variant="destructive"
                disabled={busy}
                onClick={() => cancelMutation.mutate()}
              >
                Cancel workflow
              </Button>
            ) : null}
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <h2 className="text-lg font-semibold">Nodes</h2>
        <ol className="mt-4 space-y-3">
          {nodes.map((node) => (
            <WorkflowRunNodeCard
              key={node.id}
              node={node}
              busy={busy}
              onRetry={() => retryMutation.mutate(node.node_id)}
              onRetryFrom={() => retryFromMutation.mutate(node.node_id)}
              onResume={(outcome) =>
                resumeMutation.mutate({ nodeId: node.node_id, outcome })
              }
            />
          ))}
        </ol>
      </Card>
    </div>
  );
}
