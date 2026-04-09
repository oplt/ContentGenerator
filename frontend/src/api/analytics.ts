import { apiFetch } from "./client";

export type AnalyticsOverview = {
  summary: Array<{ key: string; label: string; value: number }>;
  posts_over_time: Array<{ label: string; value: number }>;
  engagement_by_platform: Array<{ label: string; value: number }>;
  format_performance: Array<{ label: string; value: number }>;
  topic_performance: Array<{ label: string; value: number }>;
  publishing_funnel: Array<{ label: string; value: number }>;
  source_reliability: Array<{ label: string; value: number; secondary?: number | null }>;
  hook_performance: Array<{ label: string; value: number }>;
  post_time_performance: Array<{ label: string; value: number }>;
  brand_performance: Array<{ label: string; value: number }>;
  topic_to_follower_conversion: Array<{ label: string; value: number }>;
  platform_comparison: Array<{ label: string; value: number; secondary?: number | null }>;
  learning_log: Array<{ category: string; message: string; weight?: number | null; recommendation?: string | null }>;
};

export function getAnalyticsOverview() {
  return apiFetch<AnalyticsOverview>("/analytics/overview");
}

export function syncAnalytics() {
  return apiFetch<{ snapshots: number }>("/analytics/sync", {
    method: "POST",
  });
}
