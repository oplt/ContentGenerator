import { useMemo } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { sendApprovalRequest } from "../../api/approvals";
import { createContentPlan, generateContent, getContentJobs, getContentPlans } from "../../api/content";
import { getSocialAccounts } from "../../api/publishing";
import { getStoryClusters } from "../../api/stories";
import { ContentPlanPanel } from "../../components/dashboard/ContentPlanPanel";
import { SocialAccountSelector } from "../../components/dashboard/SocialAccountSelector";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { LoadingState } from "../../components/ui/LoadingState";
import { ErrorState } from "../../components/ui/ErrorState";
import { resolveQueriesStatus } from "../../components/ui/QueryBoundary";
import { useAccountSelection } from "../../hooks/useAccountSelection";
import { useDocumentVisible } from "../../hooks/useDocumentVisible";
import { useTenantScope } from "../../hooks/useTenantScope";
import { contentJobsNeedPolling, statusAwareRefetchInterval } from "../../lib/polling";
import { queryClient } from "../../lib/queryClient";
import { queryKeys } from "../../lib/queryKeys";
import { queryPolicy } from "../../lib/queryPolicy";
import { JobCard } from "./JobCard";

export type PlansTabProps = {
  active: boolean;
};

export function PlansTab({ active }: PlansTabProps) {
  const { tenantId, enabled } = useTenantScope();
  const visible = useDocumentVisible();
  const { selectedIds, setSelectedIds } = useAccountSelection(tenantId);
  const plans = useQuery({
    queryKey: queryKeys.contentPlans(tenantId ?? "none"),
    queryFn: getContentPlans,
    enabled: enabled && active,
    ...queryPolicy.moderate,
  });
  const jobs = useQuery({
    queryKey: queryKeys.contentJobs(tenantId ?? "none"),
    queryFn: ({ signal }) => getContentJobs({ signal }),
    enabled: enabled && active,
    ...queryPolicy.fast,
    refetchInterval:
      visible && active ? statusAwareRefetchInterval(10_000, contentJobsNeedPolling) : false,
  });
  const stories = useQuery({
    queryKey: queryKeys.stories(tenantId ?? "none"),
    queryFn: getStoryClusters,
    enabled: enabled && active,
    ...queryPolicy.moderate,
  });
  const socialAccounts = useQuery({
    queryKey: queryKeys.socialAccounts(tenantId ?? "none"),
    queryFn: getSocialAccounts,
    enabled: enabled && active,
    ...queryPolicy.moderate,
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

  const accounts = socialAccounts.data ?? [];
  const accountsById = useMemo(
    () => new Map(accounts.map((account) => [account.id, account])),
    [accounts],
  );
  const selectedIdSet = useMemo(() => new Set(selectedIds), [selectedIds]);
  const selectedAccounts = accounts.filter((account) => selectedIdSet.has(account.id));

  const shellStatus = resolveQueriesStatus([plans, jobs, stories, socialAccounts]);
  if (shellStatus.status === "loading") {
    return <LoadingState label="Loading content workspace" />;
  }
  if (shellStatus.status === "error") {
    return <ErrorState message="Content workspace could not be loaded." onRetry={shellStatus.retry} />;
  }

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
              accountsById={accountsById}
              onSendApproval={(id) => sendApprovalMutation.mutate(id)}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
