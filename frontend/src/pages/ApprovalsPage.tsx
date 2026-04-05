import { useMutation, useQuery } from "@tanstack/react-query";
import { sendApprovalRequest, getApprovalRequests } from "../api/approvals";
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

  if (approvals.isLoading || jobs.isLoading) {
    return <LoadingState label="Loading approvals" />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h1 className="text-2xl font-semibold">Approval Queue</h1>
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
              <h2 className="text-lg font-semibold">{approval.status}</h2>
              <p className="text-sm text-muted-foreground">{approval.recipient}</p>
            </div>
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{approval.provider}</p>
          </div>
          <div className="mt-4">
            <ApprovalTimeline approval={approval} />
          </div>
        </Card>
      ))}
    </div>
  );
}
