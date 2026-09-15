import { apiFetch, type ApiFetchOptions } from "./client";

export type Source = {
  id: string;
  name: string;
  source_type: string;
  url: string;
  parser_type: string;
  category: string;
  source_tier: string;
  content_vertical: string;
  freshness_decay_hours: number;
  legal_risk: boolean;
  rate_limit_rph: number | null;
  tier1_confirmation_required: boolean;
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

export type RawArticlePage = {
  items: RawArticle[];
  next_cursor: string | null;
  has_more: boolean;
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

export function updateSource(sourceId: string, payload: Record<string, unknown>) {
  return apiFetch<Source>(`/sources/${sourceId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function deleteSource(sourceId: string) {
  return apiFetch<void>(`/sources/${sourceId}`, {
    method: "DELETE",
  });
}

export function triggerIngestion(sourceId: string) {
  return apiFetch<{
    status: string;
    raw_articles_ingested: number;
    clusters_updated: number;
    fetch_run_id?: string | null;
    task_id?: string | null;
  }>(`/sources/${sourceId}/ingest`, { method: "POST" });
}

export function triggerManualPoll(sourceId: string) {
  return apiFetch<{
    status: string;
    raw_articles_ingested: number;
    clusters_updated: number;
    fetch_run_id?: string | null;
    task_id?: string | null;
  }>(`/sources/${sourceId}/manual-poll`, { method: "POST" });
}

export function disableSource(sourceId: string) {
  return apiFetch<{ source_id: string; status: string; detail: string }>(
    `/sources/${sourceId}/disable`,
    { method: "POST" }
  );
}

export function getSourceHealth(init?: ApiFetchOptions) {
  return apiFetch<SourceHealth[]>("/sources/health", init);
}

export type SourceFetchRun = {
  id: string;
  source_id: string;
  status: string;
  started_at: string | null;
  finished_at: string | null;
  http_status: number | null;
  duration_ms: number | null;
  articles_found: number;
  new_articles: number;
  error_message: string | null;
};

export function getSourceFetchRuns() {
  return apiFetch<SourceFetchRun[]>("/sources/fetch-runs");
}

export function getSourceFetchRun(fetchRunId: string, init?: ApiFetchOptions) {
  return apiFetch<SourceFetchRun>(`/sources/fetch-runs/${fetchRunId}`, init);
}

export function getRawArticles(
  { limit = 50, cursor }: { limit?: number; cursor?: string } = {},
  init?: ApiFetchOptions,
) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (cursor) params.set("cursor", cursor);
  return apiFetch<RawArticlePage>(`/sources/articles?${params.toString()}`, init);
}

export type CatalogEntry = {
  id: string;
  name: string;
  url: string;
  source_type: string;
  category: string;
  description: string;
  trust_score: number;
  polling_interval_minutes: number;
};

export function getCatalog(category?: string) {
  const qs = category ? `?category=${encodeURIComponent(category)}` : "";
  return apiFetch<CatalogEntry[]>(`/sources/catalog${qs}`);
}

export function importCatalogSource(catalogId: string) {
  return apiFetch<Source>(`/sources/catalog/${encodeURIComponent(catalogId)}/import`, {
    method: "POST",
  });
}
