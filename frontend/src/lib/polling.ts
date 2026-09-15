import type { Query } from "@tanstack/react-query";

/** Content generation job statuses that no longer need live refresh. */
export const TERMINAL_CONTENT_JOB_STATUSES = new Set([
  "completed",
  "failed",
  "cancelled",
  "canceled",
]);

/** Publishing queue statuses that no longer need live refresh. */
export const TERMINAL_PUBLISHING_STATUSES = new Set([
  "succeeded",
  "succeeded_dry_run",
  "failed",
  "cancelled",
  "canceled",
]);

/** Approval request statuses that no longer need live refresh. */
export const TERMINAL_APPROVAL_STATUSES = new Set([
  "approved",
  "rejected",
  "expired",
  "cancelled",
  "canceled",
]);

/** Brief statuses that no longer need live refresh. */
export const TERMINAL_BRIEF_STATUSES = new Set([
  "approved",
  "rejected",
  "expired",
]);

export function isDocumentVisible(): boolean {
  return typeof document === "undefined" || document.visibilityState === "visible";
}

export function hasActiveStatuses(
  items: Array<{ status: string }> | undefined,
  terminal: Set<string>
): boolean {
  if (!items || items.length === 0) {
    return false;
  }
  return items.some((item) => !terminal.has(String(item.status).toLowerCase()));
}

export function isActiveStatus(status: string | undefined, terminal: Set<string>): boolean {
  if (!status) {
    return false;
  }
  return !terminal.has(status.toLowerCase());
}

type IntervalQuery<T> = Pick<Query<T, Error, T, readonly unknown[]>, "state">;

/**
 * Poll only while the tab is visible and `isActive(data)` is true.
 * Returns `false` to stop React Query refetch intervals.
 */
export function statusAwareRefetchInterval<T>(
  intervalMs: number,
  isActive: (data: T | undefined) => boolean
): (query: IntervalQuery<T>) => number | false {
  return (query) => {
    if (!isDocumentVisible()) {
      return false;
    }
    if (!isActive(query.state.data)) {
      return false;
    }
    return intervalMs;
  };
}

export function contentJobsNeedPolling(
  jobs: Array<{ status: string }> | undefined
): boolean {
  return hasActiveStatuses(jobs, TERMINAL_CONTENT_JOB_STATUSES);
}

export function publishingJobsNeedPolling(
  jobs: Array<{ status: string }> | undefined
): boolean {
  return hasActiveStatuses(jobs, TERMINAL_PUBLISHING_STATUSES);
}

export function approvalsNeedPolling(
  approvals: Array<{ status: string }> | undefined
): boolean {
  return hasActiveStatuses(approvals, TERMINAL_APPROVAL_STATUSES);
}

export function briefsNeedPolling(
  briefs: Array<{ status: string }> | undefined
): boolean {
  if (!briefs || briefs.length === 0) {
    return false;
  }
  return briefs.some((brief) => {
    const status = String(brief.status).toLowerCase();
    return status === "pending" || status === "generating";
  });
}

export function contentJobNeedsPolling(job: { status: string } | undefined): boolean {
  return isActiveStatus(job?.status, TERMINAL_CONTENT_JOB_STATUSES);
}
