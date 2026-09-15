import { useMutation, useQuery } from "@tanstack/react-query";
import { sendApprovalRequest, getApprovalRequests } from "../../api/approvals";
import { getContentJobs } from "../../api/content";
import { ApprovalTimeline } from "../../components/dashboard/ApprovalTimeline";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { LoadingState } from "../../components/ui/LoadingState";
import { ErrorState } from "../../components/ui/ErrorState";
import { resolveQueriesStatus } from "../../components/ui/QueryBoundary";
import { useDocumentVisible } from "../../hooks/useDocumentVisible";
import { useTenantScope } from "../../hooks/useTenantScope";
import { approvalsNeedPolling, statusAwareRefetchInterval } from "../../lib/polling";
import { queryClient } from "../../lib/queryClient";
import { queryKeys } from "../../lib/queryKeys";

export type ApprovalsTabProps = {
  active: boolean;
};

export function ApprovalsTab({ active }: ApprovalsTabProps) {
  const { tenantId, enabled } = useTenantScope();
  const visible = useDocumentVisible();
  const approvals = useQuery({
    queryKey: queryKeys.approvals(tenantId ?? "none"),
    queryFn: ({ signal }) => getApprovalRequests({ signal }),
    enabled: enabled && active,
    refetchInterval:
      visible && active ? statusAwareRefetchInterval(10_000, approvalsNeedPolling) : false,
  });
  const jobs = useQuery({
    queryKey: queryKeys.contentJobs(tenantId ?? "none"),
    queryFn: ({ signal }) => getContentJobs({ signal }),
    enabled: enabled && active,
  });

  const sendMutation = useMutation({
    mutationFn: sendApprovalRequest,
    onSuccess: async () => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.approvals(tenantId) });
    },
  });

  const shellStatus = resolveQueriesStatus([approvals, jobs]);
  if (shellStatus.status === "loading") {
    return <LoadingState label="Loading approvals" />;
  }
  if (shellStatus.status === "error") {
    return <ErrorState message="Approvals could not be loaded." onRetry={shellStatus.retry} />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h2 className="text-base font-semibold">Send job for approval</h2>
        <div className="mt-4 flex flex-wrap gap-3">
          {jobs.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No content jobs available.</p>
          )}
          {jobs.data?.slice(0, 6).map((job) => (
            <Button
              key={job.id}
              variant="outline"
              onClick={() => sendMutation.mutate({ content_job_id: job.id })}
              disabled={sendMutation.isPending}
            >
              Send {job.job_type} for approval
            </Button>
          ))}
        </div>
      </Card>

      {approvals.data?.length === 0 && (
        <p className="text-sm text-muted-foreground">No approval requests yet.</p>
      )}
      {approvals.data?.map((approval) => (
        <Card key={approval.id} className="p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h3 className="text-lg font-semibold capitalize">{approval.status}</h3>
              <p className="text-sm text-muted-foreground">{approval.recipient}</p>
            </div>
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">
              {approval.provider}
            </p>
          </div>
          <div className="mt-4">
            <ApprovalTimeline approval={approval} />
          </div>
        </Card>
      ))}
    </div>
  );
}
