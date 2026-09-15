import { Link } from "react-router-dom";
import type { ContentJob } from "../../api/content";
import type { SocialAccount } from "../../api/publishing";
import { Badge } from "../../components/ui/badge";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { formatSocialAccountLabel } from "../../lib/socialAccounts";
import { JOB_STATUS_VARIANT } from "./jobStatus";

export type JobCardProps = {
  job: ContentJob;
  onSendApproval: (id: string) => void;
  accountsById: Map<string, SocialAccount>;
};

export function JobCard({ job, onSendApproval, accountsById }: JobCardProps) {
  const statusVariant = JOB_STATUS_VARIANT[job.status] ?? "muted";
  const targets = (job.target_social_account_ids ?? [])
    .map((id) => accountsById.get(id))
    .filter(Boolean);

  return (
    <Card className="p-5">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-2">
            <p className="text-sm font-medium">{job.job_type}</p>
            <Badge variant={statusVariant}>{job.status}</Badge>
          </div>
          <p className="mt-0.5 text-xs text-muted-foreground">{job.stage}</p>
          {targets.length > 0 ? (
            <p className="mt-1 text-xs text-muted-foreground">
              Accounts: {targets.map((account) => formatSocialAccountLabel(account!)).join(" · ")}
            </p>
          ) : null}
          {job.error_message && (
            <p className="mt-1 text-xs text-destructive">{job.error_message}</p>
          )}
        </div>
        <div className="flex shrink-0 items-center gap-2">
          {job.status === "completed" && (
            <Button variant="outline" size="sm" onClick={() => onSendApproval(job.id)}>
              Send for Approval
            </Button>
          )}
          <Link to={`/dashboard/content/${job.id}`}>
            <Button variant="outline" size="sm">
              Open
            </Button>
          </Link>
        </div>
      </div>
    </Card>
  );
}
