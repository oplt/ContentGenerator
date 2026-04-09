import { useMutation, useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";
import { createContentPlan } from "../api/content";
import { actionTrendCandidate, getStoryCluster, getTrendCandidates } from "../api/stories";
import { queryClient } from "../lib/queryClient";
import { Button } from "../components/ui/button";
import { Badge } from "../components/ui/badge";
import { Card } from "../components/ui/card";
import { LoadingState } from "../components/ui/LoadingState";

export default function StoryDetailPage() {
  const params = useParams();
  const story = useQuery({
    queryKey: ["stories", params.id],
    queryFn: () => getStoryCluster(params.id ?? ""),
    enabled: Boolean(params.id),
  });
  const candidates = useQuery({ queryKey: ["trend-candidates"], queryFn: getTrendCandidates });
  const planMutation = useMutation({
    mutationFn: createContentPlan,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: ["content", "plans"] });
    },
  });
  const candidateAction = useMutation({
    mutationFn: ({ candidateId, action }: { candidateId: string; action: string }) =>
      actionTrendCandidate(candidateId, { action }),
    onSuccess: async () => {
      await Promise.all([
        queryClient.invalidateQueries({ queryKey: ["trend-candidates"] }),
        queryClient.invalidateQueries({ queryKey: ["stories", params.id] }),
      ]);
    },
  });

  if (story.isLoading || !story.data) {
    return <LoadingState label="Loading trend candidate" />;
  }

  const d = story.data;
  const candidate = candidates.data?.find((item) => item.story_cluster_id === d.id);
  const scoreExplanation = candidate?.score_explanation ?? {};
  const sourceMix = scoreExplanation.source_mix_breakdown as Record<string, number> | undefined;
  const reviewReasons = (scoreExplanation.review_reasons as string[] | undefined) ?? [];
  const riskCategories = (scoreExplanation.topic_categories as string[] | undefined) ?? [];

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <div className="flex flex-col gap-4 md:flex-row md:items-start md:justify-between">
          <div>
            <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">{d.primary_topic}</p>
            <h1 className="mt-3 text-3xl font-semibold">{d.headline}</h1>
            <p className="mt-4 max-w-3xl text-sm text-muted-foreground">{d.summary}</p>
            <div className="mt-4 flex flex-wrap gap-2">
              <Badge variant={d.risk_level === "safe" ? "default" : d.risk_level === "unsafe" ? "danger" : "warning"}>
                {d.risk_level}
              </Badge>
              {d.review_risk_label && (
                <Badge variant={d.review_risk_label === "blocked" ? "danger" : d.review_risk_label === "high" ? "warning" : "muted"}>
                  Review {d.review_risk_label}
                </Badge>
              )}
              {d.content_vertical && (
                <Badge variant="muted" className="capitalize">{d.content_vertical}</Badge>
              )}
              <Badge variant="muted" className="capitalize">{d.workflow_state.replace(/_/g, " ")}</Badge>
              <Badge variant={d.worthy_for_content ? "success" : "muted"}>
                {d.worthy_for_content ? "Content-worthy" : d.awaiting_confirmation ? "Awaiting Tier 1" : "Hold"}
              </Badge>
              {d.tier1_sources_confirmed > 0 && (
                <Badge variant="muted">Tier 1 confirmed: {d.tier1_sources_confirmed}</Badge>
              )}
            </div>
            {d.block_reason && (
              <p className="mt-2 text-sm text-destructive">Blocked: {d.block_reason.replace(/_/g, " ")}</p>
            )}
            {d.review_reasons.length > 0 && (
              <p className="mt-2 text-sm text-muted-foreground">Review notes: {d.review_reasons.join(", ")}</p>
            )}
            {d.risk_flags && d.risk_flags.length > 0 && (
              <div className="mt-2 flex flex-wrap gap-1">
                {d.risk_flags.map((flag) => (
                  <Badge key={flag} variant="warning" className="text-xs">{flag}</Badge>
                ))}
              </div>
            )}
          </div>
          <Button
            disabled={planMutation.isPending || !d.worthy_for_content}
            title={!d.worthy_for_content ? "Trend candidate is blocked or not yet editorially ready" : undefined}
            onClick={() => planMutation.mutate({ story_cluster_id: d.id })}
          >
            {planMutation.isPending ? "Creating…" : "Create Asset Plan"}
          </Button>
        </div>
        {candidate && (
          <div className="mt-4 flex flex-wrap gap-2 border-t border-border pt-4">
            <Button
              variant="outline"
              disabled={candidateAction.isPending}
              onClick={() => candidateAction.mutate({ candidateId: candidate.id, action: "approve" })}
            >
              Approve Candidate
            </Button>
            <Button
              variant="outline"
              disabled={candidateAction.isPending}
              onClick={() => candidateAction.mutate({ candidateId: candidate.id, action: "hold" })}
            >
              Hold
            </Button>
            <Button
              variant="outline"
              disabled={candidateAction.isPending}
              onClick={() => candidateAction.mutate({ candidateId: candidate.id, action: "reject" })}
            >
              Reject
            </Button>
          </div>
        )}
        {d.trend_score && (
          <div className="mt-5 grid grid-cols-2 gap-3 border-t border-border pt-4 sm:grid-cols-4 lg:grid-cols-6">
            {([
              ["Score", d.trend_score.score],
              ["Freshness", d.trend_score.freshness_score],
              ["Credibility", d.trend_score.credibility_score],
              ["Velocity", d.trend_score.velocity_score],
              ["Novelty", d.trend_score.novelty_score],
              ["Audience fit", d.trend_score.audience_fit_score],
            ] as [string, number][]).map(([label, val]) => (
              <div key={label} className="text-center">
                <p className="text-lg font-semibold tabular-nums">{(val ?? 0).toFixed(2)}</p>
                <p className="text-xs text-muted-foreground">{label}</p>
              </div>
            ))}
          </div>
        )}
      </Card>
      {candidate && (
        <Card className="p-6">
          <h2 className="text-lg font-semibold">Score Explanation</h2>
          <div className="mt-4 grid gap-4 md:grid-cols-2 xl:grid-cols-4">
            <div className="rounded-2xl border border-border p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Final Score</p>
              <p className="mt-2 text-2xl font-semibold">{candidate.final_score.toFixed(2)}</p>
            </div>
            <div className="rounded-2xl border border-border p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Cross-source</p>
              <p className="mt-2 text-2xl font-semibold">{candidate.cross_source_count}</p>
            </div>
            <div className="rounded-2xl border border-border p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Velocity</p>
              <p className="mt-2 text-2xl font-semibold">{candidate.velocity_score.toFixed(2)}</p>
            </div>
            <div className="rounded-2xl border border-border p-4">
              <p className="text-xs uppercase tracking-[0.16em] text-muted-foreground">Risk Penalty</p>
              <p className="mt-2 text-2xl font-semibold">{candidate.risk_score.toFixed(2)}</p>
            </div>
          </div>
          <div className="mt-5 grid gap-4 lg:grid-cols-2">
            <div className="rounded-2xl border border-border p-4">
              <p className="text-sm font-medium">Evidence Links</p>
              <div className="mt-3 space-y-2 text-sm">
                {candidate.evidence_links.map((link) => (
                  <a key={link} className="block text-primary" href={link} target="_blank" rel="noreferrer">
                    {link}
                  </a>
                ))}
              </div>
            </div>
            <div className="rounded-2xl border border-border p-4">
              <p className="text-sm font-medium">Risk Breakdown</p>
              <div className="mt-3 flex flex-wrap gap-2">
                {reviewReasons.map((reason) => (
                  <Badge key={reason} variant="warning">{reason}</Badge>
                ))}
                {riskCategories.map((category) => (
                  <Badge key={category} variant="muted">{category}</Badge>
                ))}
              </div>
              {sourceMix && (
                <div className="mt-4 grid grid-cols-3 gap-2 text-sm text-muted-foreground">
                  <div>Tier 1: {sourceMix.tier1 ?? 0}</div>
                  <div>Signal: {sourceMix.signal ?? 0}</div>
                  <div>Amplify: {sourceMix.amplification ?? 0}</div>
                </div>
              )}
            </div>
          </div>
          {candidate.extracted_claims.length > 0 && (
            <div className="mt-5 rounded-2xl border border-border p-4">
              <p className="text-sm font-medium">Extracted Claims</p>
              <ul className="mt-3 space-y-2 text-sm text-muted-foreground">
                {candidate.extracted_claims.map((claim) => (
                  <li key={claim}>• {claim}</li>
                ))}
              </ul>
            </div>
          )}
        </Card>
      )}
      <div className="grid gap-4">
        {d.articles.map((article) => (
          <Card key={article.id} className="p-5">
            <div className="flex flex-wrap items-center gap-2 mb-1">
              <h2 className="font-semibold">{article.title}</h2>
              {article.source_tier && (
                <Badge variant={article.source_tier === "authoritative" ? "default" : "muted"} className="capitalize text-xs">
                  {article.source_tier}
                </Badge>
              )}
              {article.content_vertical && article.content_vertical !== "general" && (
                <Badge variant="muted" className="capitalize text-xs">{article.content_vertical}</Badge>
              )}
            </div>
            <p className="mt-2 text-sm text-muted-foreground">{article.summary}</p>
            <a className="mt-3 inline-block text-sm text-primary" href={article.canonical_url} target="_blank" rel="noreferrer">
              Open evidence source
            </a>
          </Card>
        ))}
      </div>
    </div>
  );
}
