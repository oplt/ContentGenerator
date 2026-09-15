import { useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { getContentJobs } from "../../api/content";
import { getPublishedPosts, getPublishingJobs, getSocialAccounts, publishNow } from "../../api/publishing";
import { PublishingStatusCard } from "../../components/dashboard/PublishingStatusCard";
import { SocialAccountSelector } from "../../components/dashboard/SocialAccountSelector";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { LoadingState } from "../../components/ui/LoadingState";
import { ErrorState } from "../../components/ui/ErrorState";
import { resolveQueriesStatus } from "../../components/ui/QueryBoundary";
import { useAccountSelection } from "../../hooks/useAccountSelection";
import { useDocumentVisible } from "../../hooks/useDocumentVisible";
import { useTenantScope } from "../../hooks/useTenantScope";
import { publishingJobsNeedPolling, statusAwareRefetchInterval } from "../../lib/polling";
import { queryClient } from "../../lib/queryClient";
import { queryKeys } from "../../lib/queryKeys";
import { queryPolicy } from "../../lib/queryPolicy";

export type PublishingTabProps = {
  active: boolean;
};

export function PublishingTab({ active }: PublishingTabProps) {
  const { tenantId, enabled } = useTenantScope();
  const visible = useDocumentVisible();
  const { selectedIds, setSelectedIds } = useAccountSelection(tenantId);
  const jobs = useQuery({
    queryKey: queryKeys.publishingJobs(tenantId ?? "none"),
    queryFn: ({ signal }) => getPublishingJobs({ signal }),
    enabled: enabled && active,
    ...queryPolicy.fast,
    refetchInterval:
      visible && active ? statusAwareRefetchInterval(10_000, publishingJobsNeedPolling) : false,
  });
  const posts = useQuery({
    queryKey: queryKeys.publishingPosts(tenantId ?? "none"),
    queryFn: getPublishedPosts,
    enabled: enabled && active,
    ...queryPolicy.moderate,
  });
  const contentJobs = useQuery({
    queryKey: queryKeys.contentJobs(tenantId ?? "none"),
    queryFn: ({ signal }) => getContentJobs({ signal }),
    enabled: enabled && active,
    ...queryPolicy.fast,
  });
  const socialAccounts = useQuery({
    queryKey: queryKeys.socialAccounts(tenantId ?? "none"),
    queryFn: getSocialAccounts,
    enabled: enabled && active,
    ...queryPolicy.moderate,
  });

  const publishMutation = useMutation({
    mutationFn: publishNow,
    onSuccess: async () => {
      if (!tenantId) return;
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: queryKeys.publishingJobs(tenantId) }),
        queryClient.invalidateQueries({ queryKey: queryKeys.publishingPosts(tenantId) }),
      ]);
    },
  });

  const accounts = socialAccounts.data ?? [];
  const accountsById = useMemo(
    () => new Map(accounts.map((account) => [account.id, account])),
    [accounts],
  );

  const shellStatus = resolveQueriesStatus([jobs, posts, contentJobs, socialAccounts]);
  if (shellStatus.status === "loading") {
    return <LoadingState label="Loading publishing workspace" />;
  }
  if (shellStatus.status === "error") {
    return <ErrorState message="Publishing data could not be loaded." onRetry={shellStatus.retry} />;
  }

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <SocialAccountSelector
          accounts={accounts}
          selectedIds={selectedIds}
          onChange={setSelectedIds}
          label="Accounts to publish"
        />
      </Card>

      <Card className="p-6">
        <h2 className="text-base font-semibold">Publish job now</h2>
        <div className="mt-4 flex flex-wrap gap-3">
          {contentJobs.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No content jobs available.</p>
          )}
          {contentJobs.data?.slice(0, 6).map((job) => (
            <Button
              key={job.id}
              variant="outline"
              onClick={() =>
                publishMutation.mutate({
                  content_job_id: job.id,
                  dry_run: true,
                  social_account_ids:
                    selectedIds.length > 0
                      ? selectedIds
                      : job.target_social_account_ids?.length
                        ? job.target_social_account_ids
                        : undefined,
                })
              }
              disabled={publishMutation.isPending}
            >
              Publish {job.id.slice(0, 8)}
            </Button>
          ))}
        </div>
      </Card>

      {jobs.data && jobs.data.length > 0 && (
        <div className="grid gap-4 lg:grid-cols-2">
          {jobs.data.map((job) => (
            <PublishingStatusCard
              key={job.id}
              job={job}
              account={job.social_account_id ? accountsById.get(job.social_account_id) : undefined}
            />
          ))}
        </div>
      )}

      <Card className="p-6">
        <h2 className="text-lg font-semibold">Published Posts</h2>
        <div className="mt-4 space-y-3">
          {posts.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No published posts yet.</p>
          )}
          {posts.data?.map((post) => (
            <div key={post.id} className="rounded-2xl border border-border bg-muted/40 p-4">
              <p className="font-medium capitalize">{post.platform}</p>
              <p className="text-sm text-muted-foreground">{post.external_url ?? "No external URL"}</p>
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
