import { useMutation, useQuery } from "@tanstack/react-query";
import { getAnalyticsOverview, syncAnalytics } from "../api/analytics";
import { AnalyticsCharts } from "../components/dashboard/AnalyticsCharts";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";

export default function AnalyticsPage() {
  const analytics = useQuery({ queryKey: ["analytics"], queryFn: getAnalyticsOverview });
  const syncMutation = useMutation({ mutationFn: syncAnalytics });

  if (analytics.isLoading || !analytics.data) {
    return <LoadingState label="Loading analytics" />;
  }

  return (
    <div className="space-y-6">
      <Card className="flex flex-col gap-4 p-6 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Analytics</h1>
          <p className="mt-2 text-sm text-muted-foreground">Normalized performance across platforms and content formats.</p>
        </div>
        <Button onClick={() => syncMutation.mutate()}>Sync Analytics</Button>
      </Card>
      <AnalyticsCharts data={analytics.data} />
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Learning Log</h2>
        <div className="mt-4 space-y-3">
          {analytics.data.learning_log.map((entry) => (
            <div key={`${entry.category}-${entry.message}`} className="rounded-2xl border border-border p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{entry.category}</p>
              <p className="mt-2 font-medium">{entry.message}</p>
              {entry.recommendation && (
                <p className="mt-1 text-sm text-muted-foreground">{entry.recommendation}</p>
              )}
            </div>
          ))}
        </div>
      </Card>
    </div>
  );
}
