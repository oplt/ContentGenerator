import { apiFetch } from "./client";

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
  return apiFetch<{ status: string; raw_articles_ingested: number; clusters_updated: number }>(
    `/sources/${sourceId}/ingest`,
    { method: "POST" }
  );
}

export function triggerManualPoll(sourceId: string) {
  return apiFetch<{ status: string; raw_articles_ingested: number; clusters_updated: number }>(
    `/sources/${sourceId}/manual-poll`,
    { method: "POST" }
  );
}

export function disableSource(sourceId: string) {
  return apiFetch<{ source_id: string; status: string; detail: string }>(
    `/sources/${sourceId}/disable`,
    { method: "POST" }
  );
}

export function getSourceHealth() {
  return apiFetch<SourceHealth[]>("/sources/health");
}

export function getRawArticles() {
  return apiFetch<RawArticle[]>("/sources/articles");
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
