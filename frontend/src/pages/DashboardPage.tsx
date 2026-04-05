import { useQuery } from "@tanstack/react-query";
import { getTrendDashboard } from "../api/stories";
import { getAnalyticsOverview } from "../api/analytics";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";
import { ErrorState } from "../components/ui/ErrorState";
import { StoryClusterCard } from "../components/dashboard/StoryClusterCard";
import { formatRelativeNumber } from "../lib/utils";

export default function DashboardPage() {
  const trends = useQuery({ queryKey: ["dashboard", "trends"], queryFn: getTrendDashboard });
  const analytics = useQuery({ queryKey: ["dashboard", "analytics"], queryFn: getAnalyticsOverview });

  if (trends.isLoading || analytics.isLoading) {
    return <LoadingState label="Loading dashboard" />;
  }
  if (trends.error || analytics.error || !trends.data || !analytics.data) {
    return <ErrorState message="Dashboard data could not be loaded." />;
  }

  return (
    <div className="space-y-6">
      <section className="grid gap-4 md:grid-cols-3">
        {analytics.data.summary.map((item) => (
          <Card key={item.key} className="p-5">
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{item.label}</p>
            <p className="mt-3 text-3xl font-semibold">{typeof item.value === "number" ? formatRelativeNumber(item.value) : item.value}</p>
          </Card>
        ))}
      </section>
      <section className="grid gap-4 xl:grid-cols-3">
        {trends.data.clusters.slice(0, 6).map((cluster) => (
          <StoryClusterCard key={cluster.id} cluster={cluster} />
        ))}
      </section>
    </div>
  );
}
