import { useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  cancelPublishingJob,
  getPublishedPosts,
  getPublishingJobs,
  getSocialAccounts,
  retryPublishingJob,
} from "../api/publishing";
import { useTenantScope } from "../hooks/useTenantScope";
import { useDocumentVisible } from "../hooks/useDocumentVisible";
import { queryClient } from "../lib/queryClient";
import { queryKeys } from "../lib/queryKeys";
import { publishingJobsNeedPolling, statusAwareRefetchInterval } from "../lib/polling";
import { queryPolicy } from "../lib/queryPolicy";
import { formatSocialAccountLabel } from "../lib/socialAccounts";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";

export default function PublishingQueuePage() {
  const { tenantId, enabled } = useTenantScope();
  const visible = useDocumentVisible();
  const jobs = useQuery({
    queryKey: queryKeys.publishingJobs(tenantId ?? "none"),
    queryFn: ({ signal }) => getPublishingJobs({ signal }),
    enabled,
    ...queryPolicy.fast,
    refetchInterval: visible
      ? statusAwareRefetchInterval(10_000, publishingJobsNeedPolling)
      : false,
  });
  const posts = useQuery({
    queryKey: queryKeys.publishingPosts(tenantId ?? "none"),
    queryFn: getPublishedPosts,
    enabled,
    ...queryPolicy.moderate,
  });
  const socialAccounts = useQuery({
    queryKey: queryKeys.socialAccounts(tenantId ?? "none"),
    queryFn: getSocialAccounts,
    enabled,
    ...queryPolicy.moderate,
  });
  const retryMutation = useMutation({
    mutationFn: retryPublishingJob,
    onSuccess: async () => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.publishingJobs(tenantId) });
    },
  });
  const cancelMutation = useMutation({
    mutationFn: cancelPublishingJob,
    onSuccess: async () => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.publishingJobs(tenantId) });
    },
  });

  const accountsById = useMemo(() => {
    return new Map((socialAccounts.data ?? []).map((account) => [account.id, account]));
  }, [socialAccounts.data]);

  if (jobs.isLoading || posts.isLoading || socialAccounts.isLoading) {
    return <LoadingState label="Loading publish queue" />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h1 className="text-2xl font-semibold">Publish Queue</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Monitor scheduled jobs, operator recovery actions, and live post outputs.
        </p>
      </Card>

      <div className="grid gap-4">
        {(jobs.data ?? []).map((job) => {
          const account = job.social_account_id
            ? accountsById.get(job.social_account_id)
            : undefined;
          return (
            <Card key={job.id} className="p-5">
              <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
                <div>
                  <h2 className="text-lg font-semibold capitalize">
                    {account ? formatSocialAccountLabel(account) : job.platform}
                  </h2>
                  <p className="text-sm text-muted-foreground">
                    {job.status} · retry #{job.retry_count}
                    {job.social_account_id
                      ? ` · account ${job.social_account_id.slice(0, 8)}`
                      : ""}
                  </p>
                  {job.failure_reason && (
                    <p className="mt-2 text-sm text-destructive">{job.failure_reason}</p>
                  )}
                  {job.recovery_actions.length > 0 && (
                    <div className="mt-3 flex flex-wrap gap-2 text-xs text-muted-foreground">
                      {job.recovery_actions.map((action) => (
                        <span key={action} className="rounded-full border px-2 py-1">
                          {action}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
                <div className="flex flex-wrap gap-2">
                  <Button
                    variant="outline"
                    onClick={() => retryMutation.mutate(job.id)}
                    disabled={retryMutation.isPending}
                  >
                    Retry
                  </Button>
                  <Button
                    variant="outline"
                    onClick={() => cancelMutation.mutate(job.id)}
                    disabled={
                      cancelMutation.isPending ||
                      !["scheduled", "pending", "failed"].includes(job.status)
                    }
                  >
                    Cancel
                  </Button>
                </div>
              </div>
            </Card>
          );
        })}
      </div>

      <Card className="p-6">
        <h2 className="text-lg font-semibold">Published Posts</h2>
        <div className="mt-4 space-y-3">
          {(posts.data ?? []).map((post) => (
            <div key={post.id} className="rounded-2xl border border-border p-4">
              <p className="font-medium capitalize">{post.platform}</p>
              <p className="text-sm text-muted-foreground">
                {post.external_url ?? "No external URL"}
              </p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
