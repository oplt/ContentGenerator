import { apiFetch } from "./client";

export type Period = "daily" | "weekly" | "monthly";

export interface RepoAssessment {
  what_it_does: string;
  evidence: string[];
  strongest_assets: string[];
  main_limitations: string[];
  best_commercial_angle: string;
  confidence: "high" | "medium" | "low";
}

export interface ProductIdeaMonetization {
  model: string;
  pricing_logic: string;
  estimated_willingness_to_pay: string;
}

export interface ProductIdeaScores {
  revenue_potential: number;
  customer_urgency: number;
  repo_leverage: number;
  speed_to_mvp: number;
  competitive_intensity: number;
}

export interface ProductIdea {
  rank: number;
  title: string;
  positioning: string;
  target_customer: string;
  pain_point: string;
  product_concept: string;
  why_this_repo_fits: string;
  required_extensions: string[];
  monetization: ProductIdeaMonetization;
  scores: ProductIdeaScores;
  time_to_mvp: string;
  key_risks: string[];
  why_now: string;
  investor_angle: string;
  v1_scope: string[];
  not_for_v1: string[];
}

export interface TrendingRepo {
  id: string;
  period: Period;
  snapshot_date: string;
  github_id: number;
  name: string;
  full_name: string;
  description: string | null;
  html_url: string;
  language: string | null;
  topics: string[];
  stars_count: number;
  forks_count: number;
  watchers_count: number;
  open_issues_count: number;
  stars_gained: number;
  rank: number;
  repo_assessment: RepoAssessment | null;
  product_ideas: ProductIdea[];
  ideas_generated_at: string | null;
  created_at: string;
}

export interface TrendingReposListResponse {
  repos: TrendingRepo[];
  period: Period;
  snapshot_date: string;
  total: number;
}

export async function getTrendingRepos(period: Period): Promise<TrendingReposListResponse> {
  return apiFetch<TrendingReposListResponse>(`/trending-repos?period=${period}`);
}

export async function refreshTrendingRepos(period: Period): Promise<TrendingReposListResponse> {
  return apiFetch<TrendingReposListResponse>(`/trending-repos/refresh?period=${period}`, {
    method: "POST",
  });
}

export async function generateProductIdeas(repoId: string): Promise<TrendingRepo> {
  return apiFetch<TrendingRepo>(`/trending-repos/${repoId}/generate-ideas`, {
    method: "POST",
  });
}

export async function sendTelegramDigest(): Promise<void> {
  await apiFetch<void>(`/trending-repos/send-digest`, { method: "POST" });
}

export interface GenerateTwitterPostResponse {
  repo_id: string;
  post_text: string;
}

export async function generateTwitterPost(repoId: string): Promise<GenerateTwitterPostResponse> {
  return apiFetch<GenerateTwitterPostResponse>(`/trending-repos/${repoId}/generate-twitter-post`, {
    method: "POST",
  });
}

export async function postToTwitter(
  repoId: string,
  postText: string
): Promise<{ status: string; external_post_url: string }> {
  return apiFetch(`/trending-repos/${repoId}/post-to-twitter`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ post_text: postText }),
  });
}
