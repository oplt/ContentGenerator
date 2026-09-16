/** Helpers for workflow run inspection links and timing. */

import type { WorkflowNodeRun } from "../../api/workflows";

export function formatDurationMs(ms: number | null | undefined): string {
  if (ms == null || Number.isNaN(ms)) return "—";
  if (ms < 1000) return `${ms}ms`;
  const seconds = ms / 1000;
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const rem = seconds - minutes * 60;
  return `${minutes}m ${rem.toFixed(0)}s`;
}

export function approvalRequestId(node: WorkflowNodeRun): string | null {
  const raw = node.output_json?.approval_request_id;
  return typeof raw === "string" && raw.length > 0 ? raw : null;
}

export function publishingJobIds(node: WorkflowNodeRun): string[] {
  const raw = node.output_json?.job_ids;
  if (!Array.isArray(raw)) return [];
  return raw.filter((item): item is string => typeof item === "string" && item.length > 0);
}

export function claimSummary(node: WorkflowNodeRun): string | null {
  if (!node.claimed_at && !node.claim_expires_at && !node.worker_task_id) return null;
  const parts: string[] = [];
  if (node.worker_task_id) parts.push(`worker ${node.worker_task_id.slice(0, 8)}`);
  if (node.claim_expires_at) parts.push(`lease until ${node.claim_expires_at}`);
  else if (node.claimed_at) parts.push(`claimed ${node.claimed_at}`);
  return parts.join(" · ");
}
