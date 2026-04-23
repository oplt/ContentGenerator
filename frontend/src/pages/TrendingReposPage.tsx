import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Check,
  ExternalLink,
  GitFork,
  Pencil,
  RefreshCw,
  Send,
  Sparkles,
  Star,
  TrendingUp,
  Twitter,
  X,
} from "lucide-react";
import {
  getTrendingRepos,
  refreshTrendingRepos,
  generateProductIdeas,
  generateTwitterPost,
  postToTwitter,
  sendTelegramDigest,
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
            Daily digest with AI product ideas sent to your Telegram.
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
  const [generationError, setGenerationError] = useState<string | null>(null);
  const [showTwitterPanel, setShowTwitterPanel] = useState(false);
  const [twitterPost, setTwitterPost] = useState<string | null>(null);
  const [twitterError, setTwitterError] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const ideasMutation = useMutation({
    mutationFn: () => generateProductIdeas(repo.id),
    onSuccess: async (updatedRepo) => {
      setGenerationError(null);
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
    onError: (error) => {
      setGenerationError(error instanceof Error ? error.message : "Could not generate ideas.");
    },
  });

  const twitterMutation = useMutation({
    mutationFn: () => generateTwitterPost(repo.id),
    onSuccess: (data) => {
      setTwitterPost(data.post_text);
      setTwitterError(null);
      setShowTwitterPanel(true);
    },
    onError: (error) => {
      setTwitterError(error instanceof Error ? error.message : "Could not generate Twitter post.");
    },
  });

  const visibleIdeas =
    repo.product_ideas.length > 0 ? repo.product_ideas : (ideasMutation.data?.product_ideas ?? []);
  const visibleAssessment = repo.repo_assessment ?? ideasMutation.data?.repo_assessment ?? null;
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
        <div className="flex flex-col items-end gap-2 shrink-0">
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
                  {generationError ?? "Could not generate ideas."}
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
          <div className="flex flex-col items-end gap-1">
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                if (twitterPost) {
                  setShowTwitterPanel((v) => !v);
                } else {
                  twitterMutation.mutate();
                }
              }}
              disabled={twitterMutation.isPending}
            >
              <Twitter className="size-3.5" />
              {twitterMutation.isPending
                ? "Generating…"
                : twitterPost
                  ? showTwitterPanel
                    ? "Hide Post"
                    : "Show Post"
                  : "Generate Twitter Post"}
            </Button>
            {twitterMutation.isError && (
              <p className="max-w-56 text-right text-[11px] uppercase tracking-wide text-destructive">
                {twitterError ?? "Could not generate post."}
              </p>
            )}
          </div>
        </div>
      </div>

      {/* Twitter post panel */}
      {showTwitterPanel && twitterPost && (
        <div className="mt-4 border-t border-border pt-4">
          <p className="text-xs uppercase tracking-wider text-muted-foreground mb-3">
            Twitter / X Post
          </p>
          <TwitterPostCard
            repoId={repo.id}
            initialText={twitterPost}
            onReject={() => setShowTwitterPanel(false)}
          />
        </div>
      )}

      {/* Product ideas panel */}
      {hasIdeas && showIdeas && (
        <div className="mt-4 border-t border-border pt-4">
          {visibleAssessment && (
            <div className="mb-4 grid gap-3 lg:grid-cols-[1.4fr_1fr]">
              <div className="bg-muted p-4" style={{ borderRadius: "var(--radius-sm)" }}>
                <div className="mb-2 flex items-center justify-between gap-2">
                  <p className="text-xs uppercase tracking-wider text-muted-foreground">
                    Repo Assessment
                  </p>
                  <Badge variant="muted">{visibleAssessment.confidence}</Badge>
                </div>
                <p className="text-sm text-foreground leading-relaxed">
                  {visibleAssessment.what_it_does}
                </p>
                {visibleAssessment.best_commercial_angle && (
                  <p className="mt-3 text-xs text-primary">
                    Best angle: {visibleAssessment.best_commercial_angle}
                  </p>
                )}
              </div>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-1">
                <AssessmentList label="Assets" items={visibleAssessment.strongest_assets} />
                <AssessmentList label="Limitations" items={visibleAssessment.main_limitations} />
              </div>
            </div>
          )}
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
// Twitter post card
// ---------------------------------------------------------------------------

function TwitterPostCard({
  repoId,
  initialText,
  onReject,
}: {
  repoId: string;
  initialText: string;
  onReject: () => void;
}) {
  const [editText, setEditText] = useState(initialText);
  const [editing, setEditing] = useState(false);
  const [postResult, setPostResult] = useState<{ url: string; dry: boolean } | null>(null);
  const [postError, setPostError] = useState<string | null>(null);

  const postMutation = useMutation({
    mutationFn: () => postToTwitter(repoId, editText),
    onSuccess: (data) => {
      setPostError(null);
      setPostResult({
        url: data.external_post_url,
        dry: data.status === "succeeded_dry_run",
      });
    },
    onError: (error) => {
      setPostError(error instanceof Error ? error.message : "Failed to post.");
    },
  });

  return (
    <div className="bg-muted p-4 flex flex-col gap-3" style={{ borderRadius: "var(--radius-sm)" }}>
      {editing ? (
        <textarea
          className="w-full text-sm text-foreground bg-background border border-border rounded p-2 resize-none focus:outline-none focus:ring-1 focus:ring-primary"
          rows={5}
          value={editText}
          onChange={(e) => setEditText(e.target.value)}
        />
      ) : (
        <p className="text-sm text-foreground whitespace-pre-wrap leading-relaxed">{editText}</p>
      )}

      <div className="flex items-center gap-2 flex-wrap">
        {postResult ? (
          <div className="flex items-center gap-2">
            <Check className="size-3.5 text-success" />
            <span className="text-xs text-success">
              {postResult.dry ? "Posted (dry run)" : "Posted!"}
            </span>
            {postResult.url && !postResult.dry && (
              <a
                href={postResult.url}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-primary underline flex items-center gap-1"
              >
                View <ExternalLink className="size-3" />
              </a>
            )}
          </div>
        ) : (
          <>
            <Button
              size="sm"
              variant="default"
              onClick={() => postMutation.mutate()}
              disabled={postMutation.isPending || editText.trim().length === 0}
            >
              <Check className="size-3.5" />
              {postMutation.isPending ? "Posting…" : "Accept & Post"}
            </Button>
            <Button
              size="sm"
              variant="secondary"
              onClick={() => setEditing((v) => !v)}
            >
              <Pencil className="size-3.5" />
              {editing ? "Done" : "Edit"}
            </Button>
            <Button size="sm" variant="ghost" onClick={onReject}>
              <X className="size-3.5" />
              Reject
            </Button>
          </>
        )}
        {postMutation.isError && (
          <p className="text-[11px] uppercase tracking-wide text-destructive">{postError}</p>
        )}
      </div>
    </div>
  );
}

function AssessmentList({ label, items }: { label: string; items: string[] }) {
  if (items.length === 0) {
    return null;
  }

  return (
    <div className="bg-muted p-4" style={{ borderRadius: "var(--radius-sm)" }}>
      <p className="mb-2 text-xs uppercase tracking-wider text-muted-foreground">{label}</p>
      <div className="flex flex-col gap-2">
        {items.slice(0, 3).map((item) => (
          <p key={item} className="text-xs text-foreground leading-relaxed">
            {item}
          </p>
        ))}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Idea card
// ---------------------------------------------------------------------------

function IdeaCard({ idea, index }: { idea: ProductIdea; index: number }) {
  const scoreEntries = [
    ["Revenue", idea.scores.revenue_potential],
    ["Urgency", idea.scores.customer_urgency],
    ["Leverage", idea.scores.repo_leverage],
    ["MVP", idea.scores.speed_to_mvp],
  ] as const;

  return (
    <div
      className="bg-muted p-4 flex flex-col gap-2"
      style={{ borderRadius: "var(--radius-sm)" }}
    >
      <div className="flex items-baseline gap-2">
        <span className="text-xs text-muted-foreground">#{idea.rank || index}</span>
        <h3 className="text-sm font-normal text-foreground">{idea.title}</h3>
      </div>

      {idea.positioning && (
        <p className="text-xs text-primary italic leading-relaxed">{idea.positioning}</p>
      )}

      <p className="text-xs text-muted-foreground leading-relaxed">{idea.pain_point}</p>

      <p className="text-xs text-foreground leading-relaxed">{idea.product_concept}</p>

      {idea.why_this_repo_fits && (
        <p className="text-xs text-foreground/80 leading-relaxed">
          Why this repo fits: {idea.why_this_repo_fits}
        </p>
      )}

      <div className="grid grid-cols-2 gap-2 pt-1">
        {scoreEntries.map(([label, score]) => (
          <div
            key={label}
            className="border border-border px-2 py-1"
            style={{ borderRadius: "var(--radius-sm)" }}
          >
            <div className="text-[10px] uppercase tracking-wide text-muted-foreground">{label}</div>
            <div className="text-sm text-foreground">{score}/10</div>
          </div>
        ))}
      </div>

      <div className="mt-auto pt-2 border-t border-border flex flex-col gap-1">
        {idea.target_customer && (
          <div className="flex items-start gap-1.5 text-xs">
            <span className="text-muted-foreground shrink-0">Audience:</span>
            <span className="text-foreground">{idea.target_customer}</span>
          </div>
        )}
        {idea.monetization.model && (
          <div className="flex items-start gap-1.5 text-xs">
            <span className="text-muted-foreground shrink-0">Model:</span>
            <span className="text-foreground">{idea.monetization.model}</span>
          </div>
        )}
        {idea.monetization.pricing_logic && (
          <div className="flex items-start gap-1.5 text-xs">
            <span className="text-muted-foreground shrink-0">Pricing:</span>
            <span className="text-foreground">{idea.monetization.pricing_logic}</span>
          </div>
        )}
        {idea.time_to_mvp && (
          <div className="flex items-start gap-1.5 text-xs">
            <span className="text-muted-foreground shrink-0">Time:</span>
            <span className="text-foreground">{idea.time_to_mvp}</span>
          </div>
        )}
        {idea.why_now && (
          <div className="flex items-start gap-1.5 text-xs mt-1">
            <Sparkles className="size-3 text-primary shrink-0 mt-0.5" />
            <span className="text-primary italic">{idea.why_now}</span>
          </div>
        )}
      </div>
    </div>
  );
}
