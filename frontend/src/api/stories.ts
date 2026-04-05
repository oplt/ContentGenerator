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
  explainability: Record<string, string>;
  latest_trend_score: number | null;
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
  }>;
  trend_score: {
    score: number;
    freshness_score: number;
    credibility_score: number;
    momentum_score: number;
    worthiness_score: number;
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
