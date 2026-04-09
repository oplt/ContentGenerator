import { apiFetch } from "./client";

export type StoryCluster = {
  id: string;
  slug: string;
  headline: string;
  summary: string;
  primary_topic: string;
  article_count: number;
  trend_direction: string;
  worthy_for_content: boolean;
  risk_level: string;
  workflow_state: string;
  content_vertical: string;
  risk_flags: string[];
  tier1_sources_confirmed: number;
  awaiting_confirmation: boolean;
  block_reason: string | null;
  review_risk_label: string | null;
  review_reasons: string[];
  explainability: Record<string, string>;
  latest_trend_score: number | null;
};

export type TrendCandidate = {
  id: string;
  story_cluster_id: string;
  date_bucket: string;
  primary_topic: string;
  subtopics: string[];
  supporting_item_ids: string[];
  evidence_links: string[];
  extracted_claims: string[];
  cross_source_count: number;
  source_mix: Record<string, unknown>;
  velocity_score: number;
  recency_score: number;
  novelty_score: number;
  audience_fit_score: number;
  monetization_score: number;
  risk_score: number;
  final_score: number;
  status: string;
  expires_at: string | null;
  score_explanation: Record<string, unknown>;
};

export type StoryDetail = StoryCluster & {
  articles: Array<{
    id: string;
    title: string;
    summary: string | null;
    canonical_url: string;
    source_name: string;
    keywords: string[];
    topic_tags: string[];
    published_at: string | null;
    source_tier: string;
    content_vertical: string;
  }>;
  trend_score: {
    score: number;
    freshness_score: number;
    credibility_score: number;
    momentum_score: number;
    worthiness_score: number;
    velocity_score: number;
    cross_source_score: number;
    audience_fit_score: number;
    novelty_score: number;
    monetization_score: number;
    risk_penalty_score: number;
  } | null;
};

export function getStoryClusters() {
  return apiFetch<StoryCluster[]>("/stories/clusters");
}

export function getStoryCluster(id: string) {
  return apiFetch<StoryDetail>(`/stories/clusters/${id}`);
}

export function getTrendDashboard() {
  return apiFetch<{
    summary: Array<{ key: string; label: string; value: number }>;
    clusters: StoryCluster[];
  }>("/stories/trends/dashboard");
}

export function getTrendCandidates() {
  return apiFetch<TrendCandidate[]>("/stories/candidates");
}

export function actionTrendCandidate(candidateId: string, payload: { action: string; operator_note?: string | null }) {
  return apiFetch<TrendCandidate>(`/stories/candidates/${candidateId}/action`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
