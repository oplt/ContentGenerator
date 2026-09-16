import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { listWorkflowRuns } from "../api/workflows";
import { useTenantScope } from "../hooks/useTenantScope";
import { useDocumentVisible } from "../hooks/useDocumentVisible";
import { queryKeys } from "../lib/queryKeys";
import { queryPolicy } from "../lib/queryPolicy";
import { statusAwareRefetchInterval, workflowRunsNeedPolling } from "../lib/polling";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";

function runVariant(status: string): "muted" | "success" | "warning" | "danger" {
  if (status === "succeeded") return "success";
  if (status === "failed" || status === "cancelled") return "danger";
  if (status === "waiting") return "warning";
  return "muted";
}

export default function WorkflowRunsPage() {
  const { tenantId, enabled } = useTenantScope();
  const visible = useDocumentVisible();
  const runs = useQuery({
    queryKey: queryKeys.workflowRuns(tenantId ?? "none"),
    queryFn: ({ signal }) => listWorkflowRuns({ limit: 50 }, { signal }),
    enabled,
    ...queryPolicy.fast,
    refetchInterval: visible
      ? statusAwareRefetchInterval(8_000, workflowRunsNeedPolling)
      : false,
  });

  if (runs.isLoading) return <LoadingState label="Loading workflow runs" />;
  if (runs.isError) {
    return <ErrorState title="Could not load runs" message="Retry shortly." />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h1 className="text-2xl font-semibold">Workflow runs</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Monitor execution status, waiting approvals, and node-level progress.
        </p>
      </Card>

      <div className="grid gap-3">
        {(runs.data ?? []).length === 0 && (
          <Card className="p-5 text-sm text-muted-foreground">No runs yet.</Card>
        )}
        {(runs.data ?? []).map((run) => (
          <Card key={run.id} className="p-5">
            <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
              <div>
                <div className="flex items-center gap-2">
                  <h2 className="font-semibold">{run.id.slice(0, 8)}</h2>
                  <Badge variant={runVariant(run.status)}>{run.status}</Badge>
                </div>
                <p className="mt-1 text-sm text-muted-foreground">
                  {run.trigger_type}
                  {run.started_at ? ` · started ${new Date(run.started_at).toLocaleString()}` : ""}
                  {run.error_message ? ` · ${run.error_message}` : ""}
                </p>
              </div>
              <Button asChild variant="outline">
                <Link to={`/dashboard/runs/${run.id}`}>Open</Link>
              </Button>
            </div>
          </Card>
        ))}
      </div>
    </div>
  );
}
