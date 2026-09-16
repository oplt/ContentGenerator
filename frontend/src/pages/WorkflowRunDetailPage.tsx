import { Link, useParams } from "react-router-dom";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  advanceWorkflowRun,
  getWorkflowRun,
  resumeWorkflowRun,
} from "../api/workflows";
import { useTenantScope } from "../hooks/useTenantScope";
import { useDocumentVisible } from "../hooks/useDocumentVisible";
import { queryClient } from "../lib/queryClient";
import { queryKeys } from "../lib/queryKeys";
import { queryPolicy } from "../lib/queryPolicy";
import { statusAwareRefetchInterval, workflowRunNeedsPolling } from "../lib/polling";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";

function nodeVariant(status: string): "muted" | "success" | "warning" | "danger" {
  if (status === "succeeded") return "success";
  if (status === "failed" || status === "cancelled") return "danger";
  if (status === "waiting" || status === "ready" || status === "running") return "warning";
  if (status === "skipped") return "muted";
  return "muted";
}

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

  const resumeMutation = useMutation({
    mutationFn: (payload: { resume_token: string; outcome: string }) =>
      resumeWorkflowRun(payload),
    onSuccess: invalidate,
  });

  if (detail.isLoading) return <LoadingState label="Loading run" />;
  if (detail.isError || !detail.data) {
    return <ErrorState title="Run not found" message="It may have been deleted." />;
  }

  const { run, nodes } = detail.data;
  const waiting = nodes.find((node) => node.status === "waiting" && node.resume_token);

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <Button asChild variant="ghost" size="sm" className="mb-2 px-0">
          <Link to="/dashboard/runs">Back to runs</Link>
        </Button>
        <div className="flex flex-col gap-3 md:flex-row md:items-start md:justify-between">
          <div>
            <h1 className="text-2xl font-semibold">Run {run.id.slice(0, 8)}</h1>
            <p className="mt-2 text-sm text-muted-foreground">
              {run.trigger_type} · {run.status}
              {run.correlation_id ? ` · ${run.correlation_id}` : ""}
            </p>
            {run.error_message && (
              <p className="mt-2 text-sm text-destructive">{run.error_message}</p>
            )}
          </div>
          <div className="flex flex-wrap gap-2">
            <Button
              variant="secondary"
              disabled={advanceMutation.isPending}
              onClick={() => advanceMutation.mutate()}
            >
              Advance
            </Button>
            {waiting?.resume_token && (
              <>
                <Button
                  variant="primary"
                  disabled={resumeMutation.isPending}
                  onClick={() =>
                    resumeMutation.mutate({
                      resume_token: waiting.resume_token!,
                      outcome: waiting.node_type === "approval" ? "approved" : "received",
                    })
                  }
                >
                  Resume ({waiting.node_type})
                </Button>
                {waiting.node_type === "approval" && (
                  <Button
                    variant="destructive"
                    disabled={resumeMutation.isPending}
                    onClick={() =>
                      resumeMutation.mutate({
                        resume_token: waiting.resume_token!,
                        outcome: "rejected",
                      })
                    }
                  >
                    Reject
                  </Button>
                )}
              </>
            )}
          </div>
        </div>
      </Card>

      <Card className="p-5">
        <h2 className="text-lg font-semibold">Nodes</h2>
        <ol className="mt-4 space-y-3">
          {nodes.map((node) => (
            <li key={node.id} className="rounded border border-border p-4">
              <div className="flex items-center justify-between gap-3">
                <div>
                  <p className="font-medium">
                    {node.node_id} · {node.node_type}
                  </p>
                  <p className="text-sm text-muted-foreground">
                    attempt {node.attempt}
                    {node.waiting_reason ? ` · ${node.waiting_reason}` : ""}
                  </p>
                </div>
                <Badge variant={nodeVariant(node.status)}>{node.status}</Badge>
              </div>
              {node.error_json && (
                <p className="mt-2 text-sm text-destructive">
                  {String(node.error_json.message ?? JSON.stringify(node.error_json))}
                </p>
              )}
              <div className="mt-3 grid gap-2 md:grid-cols-2">
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Inputs</p>
                  <pre className="mt-1 max-h-40 overflow-auto rounded bg-muted/40 p-2 text-xs">
                    {JSON.stringify(node.input_json ?? {}, null, 2)}
                  </pre>
                </div>
                <div>
                  <p className="text-xs font-medium text-muted-foreground">Outputs</p>
                  <pre className="mt-1 max-h-40 overflow-auto rounded bg-muted/40 p-2 text-xs">
                    {JSON.stringify(node.output_json ?? {}, null, 2)}
                  </pre>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}
