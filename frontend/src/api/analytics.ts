import { apiFetch } from "./client";

export type AnalyticsOverview = {
  summary: Array<{ key: string; label: string; value: number }>;
  posts_over_time: Array<{ label: string; value: number }>;
  engagement_by_platform: Array<{ label: string; value: number }>;
  format_performance: Array<{ label: string; value: number }>;
  topic_performance: Array<{ label: string; value: number }>;
  publishing_funnel: Array<{ label: string; value: number }>;
  source_reliability: Array<{ label: string; value: number; secondary?: number | null }>;
};

export function getAnalyticsOverview() {
  return apiFetch<AnalyticsOverview>("/analytics/overview");
}

export function syncAnalytics() {
  return apiFetch<{ snapshots: number }>("/analytics/sync", {
    method: "POST",
  });
}
