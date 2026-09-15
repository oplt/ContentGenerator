import { useMutation, useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { sendApprovalRequest, getApprovalRequests } from "../../api/approvals";
import { createContentPlan, generateContent, getContentJobs, getContentPlans, type ContentJob } from "../../api/content";
import { getPublishedPosts, getPublishingJobs, getSocialAccounts, publishNow, type SocialAccount } from "../../api/publishing";
import { getStoryClusters } from "../../api/stories";
import { queryClient } from "../../lib/queryClient";
import { Badge } from "../../components/ui/badge";
import { ApprovalTimeline } from "../../components/dashboard/ApprovalTimeline";
import { ContentPlanPanel } from "../../components/dashboard/ContentPlanPanel";
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
import {
  approvalsNeedPolling,
  contentJobsNeedPolling,
  publishingJobsNeedPolling,
  statusAwareRefetchInterval,
} from "../../lib/polling";
import { formatSocialAccountLabel } from "../../lib/socialAccounts";
import { queryKeys } from "../../lib/queryKeys";

const JOB_STATUS_VARIANT: Record<string, "default" | "success" | "warning" | "muted"> = {
  pending: "muted",
  running: "warning",
  completed: "success",
  failed: "warning",
};

export function JobCard({
  job,
  onSendApproval,
  accounts,
}: {
  job: ContentJob;
  onSendApproval: (id: string) => void;
  accounts: SocialAccount[];
}) {
  const statusVariant = JOB_STATUS_VARIANT[job.status] ?? "muted";
  const targets = (job.target_social_account_ids ?? [])
    .map((id) => accounts.find((account) => account.id === id))
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
            <Button
              variant="outline"
              size="sm"
              onClick={() => onSendApproval(job.id)}
            >
              Send for Approval
            </Button>
          )}
          <Link to={`/dashboard/content/${job.id}`}>
            <Button variant="outline" size="sm">Open</Button>
          </Link>
        </div>
      </div>
    </Card>
  );
}

// ─── Plans + Jobs tab ────────────────────────────────────────────────────────

export function PlansTab({ active }: { active: boolean }) {
  const { tenantId, enabled } = useTenantScope();
  const visible = useDocumentVisible();
  const { selectedIds, setSelectedIds } = useAccountSelection(tenantId);
  const plans = useQuery({
    queryKey: queryKeys.contentPlans(tenantId ?? "none"),
    queryFn: getContentPlans,
    enabled: enabled && active,
  });
  const jobs = useQuery({
    queryKey: queryKeys.contentJobs(tenantId ?? "none"),
    queryFn: ({ signal }) => getContentJobs({ signal }),
    enabled: enabled && active,
    refetchInterval:
      visible && active
        ? statusAwareRefetchInterval(10_000, contentJobsNeedPolling)
        : false,
  });
  const stories = useQuery({
    queryKey: queryKeys.stories(tenantId ?? "none"),
    queryFn: getStoryClusters,
    enabled: enabled && active,
  });
  const socialAccounts = useQuery({
    queryKey: queryKeys.socialAccounts(tenantId ?? "none"),
    queryFn: getSocialAccounts,
    enabled: enabled && active,
  });

  const createPlanMutation = useMutation({
    mutationFn: createContentPlan,
    onSuccess: async () => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.contentPlans(tenantId) });
    },
  });
  const generateMutation = useMutation({
    mutationFn: generateContent,
    onSuccess: async () => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.contentJobs(tenantId) });
    },
  });
  const sendApprovalMutation = useMutation({
    mutationFn: (content_job_id: string) => sendApprovalRequest({ content_job_id }),
    onSuccess: async () => {
      if (!tenantId) return;
      await queryClient.invalidateQueries({ queryKey: queryKeys.approvals(tenantId) });
    },
  });

  const shellStatus = resolveQueriesStatus([plans, jobs, stories, socialAccounts]);
  if (shellStatus.status === "loading") {
    return <LoadingState label="Loading content queue" />;
  }
  if (shellStatus.status === "error") {
    return <ErrorState message="Content workspace could not be loaded." onRetry={shellStatus.retry} />;
  }

  const accounts = socialAccounts.data ?? [];
  const selectedAccounts = accounts.filter((account) => selectedIds.includes(account.id));

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <SocialAccountSelector
          accounts={accounts}
          selectedIds={selectedIds}
          onChange={setSelectedIds}
          label="Accounts for generation"
          description="Selection is saved for this workspace session and reused when publishing."
        />
      </Card>

      <Card className="p-6">
        <h2 className="text-base font-semibold">Create plan from story</h2>
        <div className="mt-4 flex flex-wrap gap-3">
          {stories.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No stories available yet.</p>
          )}
          {stories.data?.slice(0, 5).map((story) => (
            <Button
              key={story.id}
              variant="outline"
              onClick={() => createPlanMutation.mutate({ story_cluster_id: story.id })}
              disabled={createPlanMutation.isPending}
            >
              Plan from {story.primary_topic}
            </Button>
          ))}
        </div>
      </Card>

      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Plans</h2>
          {plans.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No content plans yet.</p>
          )}
          {plans.data?.map((plan) => (
            <ContentPlanPanel
              key={plan.id}
              plan={plan}
              selectedAccounts={selectedAccounts}
              generatePending={generateMutation.isPending}
              onGenerate={() =>
                generateMutation.mutate({
                  content_plan_id: plan.id,
                  social_account_ids: selectedIds.length > 0 ? selectedIds : undefined,
                })
              }
            />
          ))}
        </div>

        <div className="space-y-4">
          <h2 className="text-lg font-semibold">Jobs</h2>
          {jobs.data?.length === 0 && (
            <p className="text-sm text-muted-foreground">No generation jobs yet.</p>
          )}
          {jobs.data?.map((job) => (
            <JobCard
              key={job.id}
              job={job}
              accounts={accounts}
              onSendApproval={(id) => sendApprovalMutation.mutate(id)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}

// ─── Approvals tab ───────────────────────────────────────────────────────────

export function ApprovalsTab({ active }: { active: boolean }) {
  const { tenantId, enabled } = useTenantScope();
  const visible = useDocumentVisible();
  const approvals = useQuery({
    queryKey: queryKeys.approvals(tenantId ?? "none"),
    queryFn: ({ signal }) => getApprovalRequests({ signal }),
    enabled: enabled && active,
    refetchInterval:
      visible && active
        ? statusAwareRefetchInterval(10_000, approvalsNeedPolling)
        : false,
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

// ─── Publishing tab ───────────────────────────────────────────────────────────

export function PublishingTab({ active }: { active: boolean }) {
  const { tenantId, enabled } = useTenantScope();
  const visible = useDocumentVisible();
  const { selectedIds, setSelectedIds } = useAccountSelection(tenantId);
  const jobs = useQuery({
    queryKey: queryKeys.publishingJobs(tenantId ?? "none"),
    queryFn: ({ signal }) => getPublishingJobs({ signal }),
    enabled: enabled && active,
    refetchInterval:
      visible && active
        ? statusAwareRefetchInterval(10_000, publishingJobsNeedPolling)
        : false,
  });
  const posts = useQuery({
    queryKey: queryKeys.publishingPosts(tenantId ?? "none"),
    queryFn: getPublishedPosts,
    enabled: enabled && active,
  });
  const contentJobs = useQuery({
    queryKey: queryKeys.contentJobs(tenantId ?? "none"),
    queryFn: ({ signal }) => getContentJobs({ signal }),
    enabled: enabled && active,
  });
  const socialAccounts = useQuery({
    queryKey: queryKeys.socialAccounts(tenantId ?? "none"),
    queryFn: getSocialAccounts,
    enabled: enabled && active,
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

  const shellStatus = resolveQueriesStatus([jobs, posts, contentJobs, socialAccounts]);
  if (shellStatus.status === "loading") {
    return <LoadingState label="Loading publishing queue" />;
  }
  if (shellStatus.status === "error") {
    return <ErrorState message="Publishing data could not be loaded." onRetry={shellStatus.retry} />;
  }

  const accounts = socialAccounts.data ?? [];

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
              account={accounts.find((account) => account.id === job.social_account_id)}
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

// ─── Page root ────────────────────────────────────────────────────────────────

