import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { getAnalyticsOverview, syncAnalytics } from "../api/analytics";
import { getSocialAccounts } from "../api/publishing";
import { AnalyticsCharts } from "../components/dashboard/AnalyticsCharts";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { EmptyState } from "../components/ui/EmptyState";
import { HelpDisclosure } from "../components/ui/HelpDisclosure";
import { QueryBoundary } from "../components/ui/QueryBoundary";
import { useTenantScope } from "../hooks/useTenantScope";
import { formatSocialAccountLabel } from "../lib/socialAccounts";
import { queryKeys } from "../lib/queryKeys";

export default function AnalyticsPage() {
  const { tenantId, enabled } = useTenantScope();
  const [accountFilter, setAccountFilter] = useState<string>("");
  const socialAccounts = useQuery({
    queryKey: queryKeys.socialAccounts(tenantId ?? "none"),
    queryFn: getSocialAccounts,
    enabled,
  });
  const analytics = useQuery({
    queryKey: [...queryKeys.analytics(tenantId ?? "none"), accountFilter || "all"],
    queryFn: () => getAnalyticsOverview(accountFilter || null),
    enabled,
  });
  const syncMutation = useMutation({ mutationFn: syncAnalytics });

  const filterLabel = useMemo(() => {
    if (!accountFilter) return null;
    const account = (socialAccounts.data ?? []).find((item) => item.id === accountFilter);
    return account ? formatSocialAccountLabel(account) : accountFilter.slice(0, 8);
  }, [accountFilter, socialAccounts.data]);

  return (
    <div className="space-y-6">
      <Card className="flex flex-col gap-4 p-6 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-2xl font-semibold">Analytics</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Normalized performance across platforms and accounts.
            {filterLabel ? ` Filtered to ${filterLabel}.` : ""}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <label className="text-sm text-muted-foreground" htmlFor="analytics-account-filter">
            Account
          </label>
          <select
            id="analytics-account-filter"
            className="rounded-xl border border-border bg-background px-3 py-2 text-sm"
            value={accountFilter}
            onChange={(event) => setAccountFilter(event.target.value)}
          >
            <option value="">All accounts</option>
            {(socialAccounts.data ?? []).map((account) => (
              <option key={account.id} value={account.id}>
                {formatSocialAccountLabel(account)}
              </option>
            ))}
          </select>
          <Button
            disabled={syncMutation.isPending}
            onClick={() => syncMutation.mutate()}
          >
            {syncMutation.isPending ? "Syncing…" : "Sync Analytics"}
          </Button>
        </div>
      </Card>

      <HelpDisclosure summary="How analytics sync works">
        Snapshots are pulled per connected social account. Filtering scopes charts and learning log to one
        account without hiding workspace-wide sync failures—retry Sync if a provider is rate-limited.
      </HelpDisclosure>

      {syncMutation.isError ? (
        <p className="text-sm text-destructive" role="alert">
          Analytics sync failed. Check connected accounts and try again.
        </p>
      ) : null}

      <QueryBoundary
        query={analytics}
        loadingLabel="Loading analytics"
        errorMessage="Analytics overview could not be loaded."
        empty={{
          when: (data) =>
            data.learning_log.length === 0 && data.engagement_by_platform.length === 0,
          title: "No analytics yet",
          description: "Sync analytics after publishing to populate charts and the learning log.",
          action: (
            <Button variant="outline" onClick={() => syncMutation.mutate()}>
              Sync now
            </Button>
          ),
        }}
        staleHint={
          <p className="text-xs text-muted-foreground">Refreshing analytics…</p>
        }
      >
        {(data) => (
          <>
            <AnalyticsCharts data={data} />
            <Card className="p-6">
              <h2 className="text-lg font-semibold">Learning Log</h2>
              {data.learning_log.length === 0 ? (
                <EmptyState
                  title="No learning entries"
                  description="Recommendations appear after enough post performance is synced."
                />
              ) : (
                <div className="mt-4 space-y-3">
                  {data.learning_log.map((entry) => (
                    <div key={`${entry.category}-${entry.message}`} className="rounded-2xl border border-border p-4">
                      <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{entry.category}</p>
                      <p className="mt-2 font-medium">{entry.message}</p>
                      {entry.recommendation && (
                        <p className="mt-1 text-sm text-muted-foreground">{entry.recommendation}</p>
                      )}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          </>
        )}
      </QueryBoundary>
    </div>
  );
}
