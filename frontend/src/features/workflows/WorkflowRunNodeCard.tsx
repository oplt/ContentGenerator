import { Link } from "react-router-dom";
import type { WorkflowNodeRun } from "../../api/workflows";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import {
  approvalRequestId,
  claimSummary,
  formatDurationMs,
  publishingJobIds,
} from "./runInspection";

function nodeVariant(status: string): "muted" | "success" | "warning" | "danger" {
  if (status === "succeeded") return "success";
  if (status === "failed" || status === "cancelled") return "danger";
  if (status === "waiting" || status === "ready" || status === "running") return "warning";
  return "muted";
}

type Props = {
  node: WorkflowNodeRun;
  busy: boolean;
  onRetry: () => void;
  onRetryFrom: () => void;
  onResume: (outcome: string) => void;
};

export function WorkflowRunNodeCard({ node, busy, onRetry, onRetryFrom, onResume }: Props) {
  const approvalId = approvalRequestId(node);
  const jobIds = publishingJobIds(node);
  const claim = claimSummary(node);
  const taskIds = node.task_execution_ids?.length
    ? node.task_execution_ids
    : node.task_execution_id
      ? [node.task_execution_id]
      : [];

  return (
    <li className="rounded border border-border p-4">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <p className="font-medium">
            {node.node_id} · {node.node_type}
          </p>
          <p className="text-sm text-muted-foreground">
            attempt {node.attempt}
            {node.duration_ms != null ? ` · ${formatDurationMs(node.duration_ms)}` : ""}
            {node.waiting_reason ? ` · ${node.waiting_reason}` : ""}
            {node.next_attempt_at ? ` · retry at ${node.next_attempt_at}` : ""}
            {node.error_class ? ` · ${node.error_class}` : ""}
            {node.cancellation_requested ? " · cancel requested" : ""}
          </p>
          {claim ? <p className="mt-1 text-xs text-muted-foreground">Claim: {claim}</p> : null}
          {taskIds.length > 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">
              TaskExecution: {taskIds.map((id) => id.slice(0, 8)).join(", ")}
            </p>
          ) : null}
        </div>
        <Badge variant={nodeVariant(node.status)}>{node.status}</Badge>
      </div>

      {(node.error_json || node.last_error) && (
        <p className="mt-2 text-sm text-destructive">
          {node.last_error ||
            String(node.error_json?.message ?? JSON.stringify(node.error_json))}
        </p>
      )}

      <div className="mt-3 flex flex-wrap gap-2">
        {node.can_retry ? (
          <>
            <Button size="sm" variant="secondary" disabled={busy} onClick={onRetry}>
              Retry node
            </Button>
            <Button size="sm" variant="secondary" disabled={busy} onClick={onRetryFrom}>
              Retry from here
            </Button>
          </>
        ) : null}
        {node.can_resume ? (
          <>
            <Button
              size="sm"
              disabled={busy}
              onClick={() =>
                onResume(node.node_type === "approval" ? "approved" : "received")
              }
            >
              Resume
            </Button>
            {node.node_type === "approval" ? (
              <Button
                size="sm"
                variant="destructive"
                disabled={busy}
                onClick={() => onResume("rejected")}
              >
                Reject
              </Button>
            ) : null}
          </>
        ) : null}
        {approvalId ? (
          <Button asChild size="sm" variant="ghost">
            <Link to="/dashboard/approvals">Inspect approval</Link>
          </Button>
        ) : null}
        {jobIds.map((jobId) => (
          <Button key={jobId} asChild size="sm" variant="ghost">
            <Link to="/dashboard/publishing">Open PublishingJob {jobId.slice(0, 8)}</Link>
          </Button>
        ))}
      </div>

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
  );
}
