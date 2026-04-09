import { useMutation, useQuery } from "@tanstack/react-query";
import { actionApprovalRequest, getApprovalRequests, resendApprovalRequest, sendApprovalRequest } from "../api/approvals";
import { getContentJobs } from "../api/content";
import { queryClient } from "../lib/queryClient";
import { ApprovalTimeline } from "../components/dashboard/ApprovalTimeline";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";

export default function ApprovalsPage() {
  const approvals = useQuery({ queryKey: ["approvals"], queryFn: getApprovalRequests, refetchInterval: 10_000 });
  const jobs = useQuery({ queryKey: ["content", "jobs"], queryFn: getContentJobs });
  const sendMutation = useMutation({
    mutationFn: sendApprovalRequest,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
  const resendMutation = useMutation({
    mutationFn: resendApprovalRequest,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["approvals"] });
    },
  });
  const actionMutation = useMutation({
    mutationFn: ({ requestId, action, feedback }: { requestId: string; action: string; feedback?: string }) =>
      actionApprovalRequest(requestId, { action, feedback }),
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["approvals"] });
      await queryClient.invalidateQueries({ queryKey: ["content", "jobs"] });
      await queryClient.invalidateQueries({ queryKey: ["publishing", "jobs"] });
    },
  });

  if (approvals.isLoading || jobs.isLoading) {
    return <LoadingState label="Loading approvals" />;
  }

  const pending = approvals.data?.filter((approval) => approval.status === "pending") ?? [];
  const expired = approvals.data?.filter((approval) => approval.status === "expired") ?? [];
  const callbackFailures = approvals.data?.filter((approval) => approval.callback_verification_failures > 0) ?? [];

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h1 className="text-2xl font-semibold">Approval Queue</h1>
        <div className="mt-3 grid gap-3 md:grid-cols-3">
          <div className="rounded-lg border p-3">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Pending</p>
            <p className="mt-1 text-2xl font-semibold">{pending.length}</p>
          </div>
          <div className="rounded-lg border p-3">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Expired</p>
            <p className="mt-1 text-2xl font-semibold">{expired.length}</p>
          </div>
          <div className="rounded-lg border p-3">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Callback Failures</p>
            <p className="mt-1 text-2xl font-semibold">{callbackFailures.length}</p>
          </div>
        </div>
        <div className="mt-5 flex flex-wrap gap-3">
          {jobs.data?.slice(0, 6).map((job) => (
            <Button key={job.id} variant="outline" onClick={() => sendMutation.mutate({ content_job_id: job.id })}>
              Send {job.job_type} for approval
            </Button>
          ))}
        </div>
      </Card>
      {approvals.data?.map((approval) => (
        <Card key={approval.id} className="p-6">
          <div className="flex items-center justify-between gap-3">
            <div>
              <h2 className="text-lg font-semibold capitalize">{approval.status}</h2>
              <p className="text-sm text-muted-foreground">{approval.approval_type} • {approval.recipient}</p>
              {approval.risk_label && (
                <p className="mt-1 text-xs uppercase tracking-[0.16em] text-muted-foreground">
                  Risk review: {approval.risk_label}
                </p>
              )}
            </div>
            <div className="text-right">
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{approval.provider}</p>
              {approval.callback_verification_failures > 0 && (
                <p className="mt-1 text-xs text-destructive">
                  {approval.callback_verification_failures} callback failure{approval.callback_verification_failures === 1 ? "" : "s"}
                </p>
              )}
            </div>
          </div>
          <div className="mt-4 flex flex-wrap gap-2 text-xs text-muted-foreground">
            {approval.buttons_json.map((button) => (
              <span key={button} className="rounded-full border px-2 py-1">
                {button}
              </span>
            ))}
          </div>
          {approval.callback_last_error && (
            <div className="mt-4 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm text-destructive">
              Callback error: {approval.callback_last_error}
            </div>
          )}
          <div className="mt-4">
            <ApprovalTimeline approval={approval} />
          </div>
          <div className="mt-4 flex gap-3">
            <Button
              variant="outline"
              onClick={() => resendMutation.mutate(approval.id)}
              disabled={resendMutation.isPending}
            >
              Resend
            </Button>
            <Button
              variant="outline"
              onClick={() => actionMutation.mutate({ requestId: approval.id, action: "approve" })}
              disabled={actionMutation.isPending || approval.status === "approved"}
            >
              Approve
            </Button>
            <Button
              variant="outline"
              onClick={() => actionMutation.mutate({ requestId: approval.id, action: "regenerate" })}
              disabled={actionMutation.isPending || approval.approval_type === "topic"}
            >
              Regenerate
            </Button>
            <Button
              variant="outline"
              onClick={() => actionMutation.mutate({ requestId: approval.id, action: "reject" })}
              disabled={actionMutation.isPending || approval.status === "rejected"}
            >
              Reject
            </Button>
            {approval.expires_at && <p className="text-sm text-muted-foreground">Expires: {new Date(approval.expires_at).toLocaleString()}</p>}
          </div>
        </Card>
      ))}
    </div>
  );
}
