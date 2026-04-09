import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  ExternalLink,
  GitFork,
  RefreshCw,
  Sparkles,
  Star,
  TrendingUp,
} from "lucide-react";
import {
  getTrendingRepos,
  refreshTrendingRepos,
  generateProductIdeas,
  type Period,
  type TrendingRepo,
  type ProductIdea,
  type TrendingReposListResponse,
} from "../api/trending";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "../components/ui/tabs";
import { Badge } from "../components/ui/badge";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";
import { EmptyState } from "../components/ui/EmptyState";

const PERIOD_LABELS: Record<Period, string> = {
  daily: "Today",
  weekly: "This Week",
  monthly: "This Month",
};

export default function TrendingReposPage() {
  const [period, setPeriod] = useState<Period>("daily");
  const queryClient = useQueryClient();

  const { data, isLoading, isError } = useQuery({
    queryKey: ["trending-repos", period],
    queryFn: () => getTrendingRepos(period),
    staleTime: 1000 * 60 * 5, // 5 min
  });

  const refreshMutation = useMutation({
    mutationFn: () => refreshTrendingRepos(period),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["trending-repos", period] });
    },
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
            Daily digest with AI product ideas sent to your Telegram.
          </p>
        </div>
        <Button
          variant="secondary"
          size="sm"
          onClick={() => refreshMutation.mutate()}
          disabled={refreshMutation.isPending}
          className="shrink-0"
        >
          <RefreshCw className={`size-4 ${refreshMutation.isPending ? "animate-spin" : ""}`} />
          Refresh
        </Button>
      </div>

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
            {isLoading ? (
              <LoadingState label="Fetching trending repos…" />
            ) : isError ? (
              <EmptyState
                title="Failed to load"
                description="Could not fetch trending repos. Try refreshing."
              />
            ) : !data || data.repos.length === 0 ? (
              <EmptyState
                title="No data yet"
                description={`No trending repos fetched for ${PERIOD_LABELS[p].toLowerCase()} yet. Click Refresh to fetch now.`}
              />
            ) : (
              <div className="flex flex-col gap-4">
                {data.repos.map((repo) => (
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

// ---------------------------------------------------------------------------
// Repo card
// ---------------------------------------------------------------------------

function RepoCard({ repo }: { repo: TrendingRepo }) {
  const [showIdeas, setShowIdeas] = useState(false);
  const queryClient = useQueryClient();

  const ideasMutation = useMutation({
    mutationFn: () => generateProductIdeas(repo.id),
    onSuccess: async (updatedRepo) => {
      setShowIdeas(true);
      queryClient.setQueriesData(
        { queryKey: ["trending-repos"] },
        (existing: TrendingReposListResponse | undefined) => {
          if (!existing) {
            return existing;
          }
          return {
            ...existing,
            repos: existing.repos.map((existingRepo) =>
              existingRepo.id === updatedRepo.id ? updatedRepo : existingRepo
            ),
          };
        }
      );
      await queryClient.invalidateQueries({ queryKey: ["trending-repos"] });
    },
  });

  const visibleIdeas =
    repo.product_ideas.length > 0 ? repo.product_ideas : (ideasMutation.data?.product_ideas ?? []);
  const hasIdeas = visibleIdeas.length > 0;

  return (
    <Card className="p-5">
      {/* Top row */}
      <div className="flex items-start gap-4">
        {/* Rank badge */}
        <div className="flex h-8 w-8 shrink-0 items-center justify-center bg-muted text-xs font-normal text-muted-foreground" style={{ borderRadius: "var(--radius-sm)" }}>
          #{repo.rank}
        </div>

        {/* Repo info */}
        <div className="flex-1 min-w-0">
          <div className="flex flex-wrap items-center gap-2 mb-1">
            <a
              href={repo.html_url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-base font-normal text-foreground hover:text-primary transition-colors flex items-center gap-1"
            >
              {repo.full_name}
              <ExternalLink className="size-3.5 shrink-0" />
            </a>
            {repo.language && (
              <Badge variant="muted">{repo.language}</Badge>
            )}
          </div>

          {repo.description && (
            <p className="text-sm text-muted-foreground line-clamp-2 mb-3">
              {repo.description}
            </p>
          )}

          {/* Topics */}
          {repo.topics.length > 0 && (
            <div className="flex flex-wrap gap-1.5 mb-3">
              {repo.topics.slice(0, 6).map((t) => (
                <span
                  key={t}
                  className="text-xs text-muted-foreground border border-border px-2 py-0.5"
                  style={{ borderRadius: "var(--radius-sm)" }}
                >
                  {t}
                </span>
              ))}
            </div>
          )}

          {/* Stats row */}
          <div className="flex flex-wrap items-center gap-4 text-xs text-muted-foreground">
            <span className="flex items-center gap-1">
              <Star className="size-3.5 text-warning" />
              {repo.stars_count.toLocaleString()} stars
            </span>
            {repo.stars_gained > 0 && (
              <span className="flex items-center gap-1 text-success">
                <TrendingUp className="size-3.5" />
                +{repo.stars_gained.toLocaleString()} in period
              </span>
            )}
            <span className="flex items-center gap-1">
              <GitFork className="size-3.5" />
              {repo.forks_count.toLocaleString()} forks
            </span>
            {repo.ideas_generated_at && (
              <span className="text-muted-foreground/60">
                Ideas generated {new Date(repo.ideas_generated_at).toLocaleDateString()}
              </span>
            )}
          </div>
        </div>

        {/* Actions */}
        <div className="flex items-center gap-2 shrink-0">
          {!hasIdeas ? (
            <div className="flex flex-col items-end gap-2">
              <Button
                variant="outline"
                size="sm"
                onClick={() => ideasMutation.mutate()}
                disabled={ideasMutation.isPending}
              >
                <Sparkles className="size-3.5" />
                {ideasMutation.isPending ? "Generating…" : "Generate Ideas"}
              </Button>
              {ideasMutation.isError && (
                <p className="max-w-56 text-right text-[11px] uppercase tracking-wide text-destructive">
                  Could not generate ideas. Check backend logs or LLM configuration.
                </p>
              )}
            </div>
          ) : (
            <Button
              variant="ghost"
              size="sm"
              onClick={() => setShowIdeas((v) => !v)}
            >
              <Sparkles className="size-3.5 text-primary" />
              {showIdeas ? "Hide Ideas" : `${visibleIdeas.length} Ideas`}
            </Button>
          )}
        </div>
      </div>

      {/* Product ideas panel */}
      {hasIdeas && showIdeas && (
        <div className="mt-4 border-t border-border pt-4">
          <p className="text-xs uppercase tracking-wider text-muted-foreground mb-3">
            AI-Generated Product Ideas
          </p>
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
            {visibleIdeas.map((idea, idx) => (
              <IdeaCard key={idx} idea={idea} index={idx + 1} />
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Idea card
// ---------------------------------------------------------------------------

function IdeaCard({ idea, index }: { idea: ProductIdea; index: number }) {
  return (
    <div
      className="bg-muted p-4 flex flex-col gap-2"
      style={{ borderRadius: "var(--radius-sm)" }}
    >
      <div className="flex items-baseline gap-2">
        <span className="text-xs text-muted-foreground">#{index}</span>
        <h3 className="text-sm font-normal text-foreground">{idea.title}</h3>
      </div>

      <p className="text-xs text-muted-foreground leading-relaxed">{idea.problem}</p>

      <p className="text-xs text-foreground leading-relaxed">{idea.solution}</p>

      <div className="mt-auto pt-2 border-t border-border flex flex-col gap-1">
        {idea.target_audience && (
          <div className="flex items-start gap-1.5 text-xs">
            <span className="text-muted-foreground shrink-0">Audience:</span>
            <span className="text-foreground">{idea.target_audience}</span>
          </div>
        )}
        {idea.monetization && (
          <div className="flex items-start gap-1.5 text-xs">
            <span className="text-muted-foreground shrink-0">Model:</span>
            <span className="text-foreground">{idea.monetization}</span>
          </div>
        )}
        {idea.wow_factor && (
          <div className="flex items-start gap-1.5 text-xs mt-1">
            <Sparkles className="size-3 text-primary shrink-0 mt-0.5" />
            <span className="text-primary italic">{idea.wow_factor}</span>
          </div>
        )}
      </div>
    </div>
  );
}
