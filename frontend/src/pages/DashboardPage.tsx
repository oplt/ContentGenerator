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
            <span className="mt-1 text-xs uppercase tracking-[0.14em] text-muted-foreground">
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
  const trends = useQuery({ queryKey: ["dashboard", "trends"], queryFn: getTrendDashboard });
  const analytics = useQuery({ queryKey: ["dashboard", "analytics"], queryFn: getAnalyticsOverview });
  const sources = useQuery({ queryKey: ["sources"], queryFn: getSources });
  const stories = useQuery({ queryKey: ["stories"], queryFn: getStoryClusters });
  const plans = useQuery({ queryKey: ["content", "plans"], queryFn: getContentPlans });
  const jobs = useQuery({ queryKey: ["content", "jobs"], queryFn: getContentJobs });
  const approvals = useQuery({ queryKey: ["approvals"], queryFn: getApprovalRequests });
  const posts = useQuery({ queryKey: ["publishing", "posts"], queryFn: getPublishedPosts });
  const health = useQuery({ queryKey: ["health", "ready"], queryFn: getHealthReadiness, refetchInterval: 15_000 });

  if (trends.isLoading || analytics.isLoading) {
    return <LoadingState label="Loading dashboard" />;
  }
  if (trends.error || analytics.error || !trends.data || !analytics.data) {
    return <ErrorState message="Dashboard data could not be loaded." />;
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
        <p className="mb-3 text-xs uppercase tracking-[0.16em] text-muted-foreground">Pipeline</p>
        <PipelineStrip stages={pipelineStages} />
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        {analytics.data.summary.map((item) => (
          <Card key={item.key} className="p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{item.label}</p>
            <p className="mt-3 text-3xl font-semibold">
              {typeof item.value === "number" ? formatRelativeNumber(item.value) : item.value}
            </p>
          </Card>
        ))}
      </section>

      {health.data && (
        <section className="grid gap-4 lg:grid-cols-3">
          <Card className="p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Readiness</p>
            <p className="mt-3 text-2xl font-semibold capitalize">{health.data.status}</p>
          </Card>
          <Card className="p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Worker Queues</p>
            <p className="mt-3 text-2xl font-semibold">{health.data.worker_status.length}</p>
          </Card>
          <Card className="p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Inference</p>
            <p className="mt-3 text-2xl font-semibold">{health.data.checks.inference}</p>
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
