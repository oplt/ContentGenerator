import type { PublishingJob, SocialAccount } from "../../api/publishing";
import { formatSocialAccountLabel } from "../../lib/socialAccounts";
import { Badge } from "../ui/badge";
import { Card } from "../ui/card";

export function PublishingStatusCard({
  job,
  account,
}: {
  job: PublishingJob;
  account?: SocialAccount | null;
}) {
  const variant =
    job.status === "succeeded"
      ? "success"
      : job.status === "manual_required" || job.account_rate_limited || job.provider_payload?.account_rate_limited === "true"
        ? "warning"
        : "muted";
  return (
    <Card className="p-4">
      <div className="flex items-start justify-between gap-4">
        <div className="min-w-0">
          <p className="text-xs font-medium text-muted-foreground">{job.platform}</p>
          <h3 className="mt-2 text-base font-semibold">
            {account ? formatSocialAccountLabel(account) : job.social_account_id
              ? `Account ${job.social_account_id.slice(0, 8)}`
              : job.idempotency_key}
          </h3>
          <p className="mt-1 text-sm text-muted-foreground">
            {job.external_post_url ?? "Awaiting provider URL"}
          </p>
          {(job.account_rate_limited || job.provider_payload?.account_rate_limited === "true") && (
            <p className="mt-1 text-xs text-amber-700 dark:text-amber-400">
              Account rate limited — retries after {job.provider_payload?.retry_after_seconds ?? "?"}s
              (other accounts unaffected)
            </p>
          )}
          {job.social_account_id ? (
            <p className="mt-1 font-mono text-xs text-muted-foreground">
              account {job.social_account_id.slice(0, 8)} · job {job.id.slice(0, 8)}
            </p>
          ) : null}
        </div>
        <Badge variant={variant}>{job.status}</Badge>
      </div>
    </Card>
  );
}
