import { apiFetch } from "./client";

export type Source = {
  id: string;
  name: string;
  source_type: string;
  url: string;
  parser_type: string;
  category: string;
  config: Record<string, string>;
  polling_interval_minutes: number;
  trust_score: number;
  active: boolean;
  failure_count: number;
  success_count: number;
  circuit_state: string;
  last_polled_at: string | null;
  last_success_at: string | null;
};

export type SourceHealth = {
  source_id: string;
  status: string;
  failure_count: number;
  success_count: number;
  circuit_state: string;
  negative_cache_until: string | null;
  last_success_at: string | null;
};

export type RawArticle = {
  id: string;
  source_id: string;
  title: string;
  summary: string | null;
  canonical_url: string;
  author: string | null;
  language: string | null;
  published_at: string | null;
  extraction_confidence: number;
};

export function getSources() {
  return apiFetch<Source[]>("/sources");
}

export function createSource(payload: Record<string, unknown>) {
  return apiFetch<Source>("/sources", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function triggerIngestion(sourceId: string) {
  return apiFetch<{ status: string; raw_articles_ingested: number; clusters_updated: number }>(
    `/sources/${sourceId}/ingest`,
    { method: "POST" }
  );
}

export function getSourceHealth() {
  return apiFetch<SourceHealth[]>("/sources/health");
}

export function getRawArticles() {
  return apiFetch<RawArticle[]>("/sources/articles");
}
