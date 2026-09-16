import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { getTrendDashboard } from "../api/stories";
import { getAnalyticsOverview } from "../api/analytics";
import { getHealthReadiness } from "../api/health";
import { getSources } from "../api/sources";
import { getStoryClusters } from "../api/stories";
import { getContentPlans, getContentJobs } from "../api/content";
import { getApprovalRequests } from "../api/approvals";
import { getPublishedPosts } from "../api/publishing";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { StoryClusterCard } from "../components/dashboard/StoryClusterCard";
import { useTenantScope } from "../hooks/useTenantScope";
import { useDocumentVisible } from "../hooks/useDocumentVisible";
import { queryKeys } from "../lib/queryKeys";
import { queryPolicy } from "../lib/queryPolicy";
import { statusAwareRefetchInterval } from "../lib/polling";
import { formatRelativeNumber } from "../lib/utils";

type PipelineStage = {
  label: string;
  count: number | undefined;
  href: string;
  active?: boolean;
};

function PipelineStrip({ stages }: { stages: PipelineStage[] }) {
  return (
    <div className="flex flex-wrap items-center gap-1">
      {stages.map((stage, i) => (
        <div key={stage.label} className="flex items-center gap-1">
          <Link
            to={stage.href}
            className="flex flex-col items-center rounded-xl border border-border bg-card px-4 py-3 text-center transition hover:border-primary/40 hover:bg-accent/40 min-w-[90px]"
          >
            <span className="text-2xl font-semibold tabular-nums">
              {stage.count ?? "—"}
            </span>
            <span className="mt-1 text-xs font-medium text-muted-foreground">
              {stage.label}
            </span>
          </Link>
          {i < stages.length - 1 && (
            <span className="text-muted-foreground/40 text-lg select-none">›</span>
          )}
        </div>
      ))}
    </div>
  );
}

export default function DashboardPage() {
  const { tenantId, enabled } = useTenantScope();
  const visible = useDocumentVisible();
  const trends = useQuery({
    queryKey: queryKeys.dashboardTrends(tenantId ?? "none"),
    queryFn: getTrendDashboard,
    enabled,
  });
  const analytics = useQuery({
    queryKey: queryKeys.dashboardAnalytics(tenantId ?? "none"),
    queryFn: () => getAnalyticsOverview(),
    enabled,
  });
  const sources = useQuery({
    queryKey: queryKeys.sources(tenantId ?? "none"),
    queryFn: getSources,
    enabled,
  });
  const stories = useQuery({
    queryKey: queryKeys.stories(tenantId ?? "none"),
    queryFn: getStoryClusters,
    enabled,
  });
  const plans = useQuery({
    queryKey: queryKeys.contentPlans(tenantId ?? "none"),
    queryFn: getContentPlans,
    enabled,
  });
  const jobs = useQuery({
    queryKey: queryKeys.contentJobs(tenantId ?? "none"),
    queryFn: getContentJobs,
    enabled,
  });
  const approvals = useQuery({
    queryKey: queryKeys.approvals(tenantId ?? "none"),
    queryFn: getApprovalRequests,
    enabled,
  });
  const posts = useQuery({
    queryKey: queryKeys.publishingPosts(tenantId ?? "none"),
    queryFn: getPublishedPosts,
    enabled,
  });
  const health = useQuery({
    queryKey: queryKeys.healthReady,
    queryFn: ({ signal }) => getHealthReadiness({ signal }),
    ...queryPolicy.health,
    refetchInterval: visible
      ? statusAwareRefetchInterval(15_000, () => true)
      : false,
  });

  if (trends.isPending || analytics.isPending) {
    return <LoadingState label="Loading dashboard" />;
  }
  if (trends.isError || analytics.isError || !trends.data || !analytics.data) {
    return (
      <ErrorState
        message="Dashboard data could not be loaded."
        onRetry={() => {
          void trends.refetch();
          void analytics.refetch();
        }}
      />
    );
  }

  const pendingApprovals = approvals.data?.filter((a) => a.status === "pending").length;
  const completedJobs = jobs.data?.filter((j) => j.status === "completed").length;

  const pipelineStages: PipelineStage[] = [
    { label: "Sources", count: sources.data?.length, href: "/dashboard/sources" },
    { label: "Stories", count: stories.data?.length, href: "/dashboard/stories" },
    { label: "Plans", count: plans.data?.length, href: "/dashboard/content?tab=plans" },
    { label: "Jobs", count: completedJobs, href: "/dashboard/content?tab=plans" },
    { label: "Approvals", count: pendingApprovals, href: "/dashboard/content?tab=approvals" },
    { label: "Published", count: posts.data?.length, href: "/dashboard/content?tab=publishing" },
  ];

  return (
    <div className="space-y-6">
      <section>
        <p className="mb-3 text-xs font-medium text-muted-foreground">Pipeline</p>
        <PipelineStrip stages={pipelineStages} />
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {analytics.data.summary.map((item) => (
          <Card key={item.key} className="p-6">
            <p className="text-xs font-medium text-muted-foreground">{item.label}</p>
            <p className="mt-3 text-3xl font-semibold">
              {typeof item.value === "number" ? formatRelativeNumber(item.value) : item.value}
            </p>
          </Card>
        ))}
      </section>

      {health.data && (
        <section className="grid gap-4 lg:grid-cols-3">
          <Card className="p-6">
            <p className="text-xs font-medium text-muted-foreground">Readiness</p>
            <p className="mt-3 text-xl font-semibold capitalize">{health.data.status}</p>
          </Card>
          <Card className="p-6">
            <p className="text-xs font-medium text-muted-foreground">Worker Queues</p>
            <p className="mt-3 text-xl font-semibold">{health.data.worker_status.length}</p>
          </Card>
          <Card className="p-6">
            <p className="text-xs font-medium text-muted-foreground">Inference</p>
            <p className="mt-3 text-xl font-semibold">{health.data.checks.inference}</p>
          </Card>
        </section>
      )}

      <section className="grid gap-4 xl:grid-cols-3">
        {trends.data.clusters.slice(0, 6).map((cluster) => (
          <StoryClusterCard key={cluster.id} cluster={cluster} />
        ))}
      </section>
    </div>
  );
}
