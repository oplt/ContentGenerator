import { apiFetch } from "./client";

export type Period = "daily" | "weekly" | "monthly";

export interface ProductIdea {
  title: string;
  problem: string;
  solution: string;
  target_audience: string;
  monetization: string;
  wow_factor: string;
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
