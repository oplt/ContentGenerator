import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { RefreshCw, Send, TrendingUp } from "lucide-react";
import {
  getTrendingRepos,
  refreshTrendingRepos,
  sendTelegramDigest,
  type Period,
} from "../api/trending";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Button } from "../components/ui/button";
import { useTenantScope } from "../hooks/useTenantScope";
import { useDeepLinkTab } from "../hooks/useDeepLinkTab";
import { queryKeys } from "../lib/queryKeys";
import { LoadingState } from "../components/ui/LoadingState";
import { EmptyState } from "../components/ui/EmptyState";
import { ErrorState } from "../components/ui/ErrorState";
import { HelpDisclosure } from "../components/ui/HelpDisclosure";
import { PERIOD_LABELS, PERIODS, RepoCard } from "../features/trending";

export default function TrendingReposPage() {
  const [period, setPeriod] = useDeepLinkTab<Period>("period", PERIODS, "daily");
  const queryClient = useQueryClient();
  const { tenantId, enabled } = useTenantScope();

  const trending = useQuery({
    queryKey: queryKeys.trendingRepos(tenantId ?? "none", period),
    queryFn: () => getTrendingRepos(period),
    enabled,
    staleTime: 1000 * 60 * 5, // 5 min
  });

  const refreshMutation = useMutation({
    mutationFn: () => refreshTrendingRepos(period),
    onSuccess: () => {
      if (!tenantId) return;
      queryClient.invalidateQueries({ queryKey: queryKeys.trendingRepos(tenantId, period) });
    },
  });

  const digestMutation = useMutation({
    mutationFn: sendTelegramDigest,
  });

  return (
    <div className="flex flex-col gap-6 p-6">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <div className="flex items-center gap-2 mb-1">
            <TrendingUp className="size-5 text-primary" />
            <h1 className="text-2xl font-normal text-foreground">Trending Repos</h1>
          </div>
          <p className="text-sm text-muted-foreground">
            Fastest-rising GitHub repositories — ranked by stars gained in the window.
          </p>
        </div>
        <div className="flex items-center gap-2 shrink-0">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => digestMutation.mutate()}
            disabled={digestMutation.isPending || digestMutation.isSuccess}
            title="Send today's digest to Telegram"
          >
            <Send className={`size-4 ${digestMutation.isPending ? "animate-pulse" : ""}`} />
            {digestMutation.isPending ? "Sending…" : digestMutation.isSuccess ? "Sent!" : "Send to Telegram"}
          </Button>
          <Button
            variant="secondary"
            size="sm"
            onClick={() => refreshMutation.mutate()}
            disabled={refreshMutation.isPending}
          >
            <RefreshCw className={`size-4 ${refreshMutation.isPending ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>
      </div>

      <HelpDisclosure summary="About digests and AI ideas">
        Daily digests with AI product ideas can be sent to Telegram. Refresh pulls the latest GitHub trending window
        for the selected period. Period choice is stored in the URL as <code className="mx-1">?period=</code>.
      </HelpDisclosure>

      {digestMutation.isError ? (
        <ErrorState message="Telegram digest could not be sent." />
      ) : null}
      {refreshMutation.isError ? (
        <ErrorState message="Refresh failed. Try again in a moment." />
      ) : null}

      {/* Period tabs */}
      <Tabs value={period} onValueChange={(v) => setPeriod(v as Period)}>
        <TabsList>
          {(Object.keys(PERIOD_LABELS) as Period[]).map((p) => (
            <TabsTrigger key={p} value={p}>
              {PERIOD_LABELS[p]}
            </TabsTrigger>
          ))}
        </TabsList>

        {(Object.keys(PERIOD_LABELS) as Period[]).map((p) => (
          <TabsContent key={p} value={p} className="mt-6">
            {period !== p ? null : trending.isPending && !trending.data ? (
              <LoadingState label="Fetching trending repos" />
            ) : trending.isError && !trending.data ? (
              <ErrorState
                message="Could not fetch trending repos."
                onRetry={() => {
                  void trending.refetch();
                }}
              />
            ) : !trending.data || trending.data.repos.length === 0 ? (
              <EmptyState
                title="No data yet"
                description={`No trending repos fetched for ${PERIOD_LABELS[p].toLowerCase()} yet.`}
                action={
                  <Button variant="outline" onClick={() => refreshMutation.mutate()}>
                    Refresh now
                  </Button>
                }
              />
            ) : (
              <div className="flex flex-col gap-4">
                {trending.isFetching ? (
                  <p className="text-xs text-muted-foreground">Refreshing trending repos…</p>
                ) : null}
                {trending.data.repos.map((repo) => (
                  <RepoCard key={repo.id} repo={repo} />
                ))}
              </div>
            )}
          </TabsContent>
        ))}
      </Tabs>
    </div>
  );
}

