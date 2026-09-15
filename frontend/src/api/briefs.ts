import { apiFetch, type ApiFetchOptions } from "./client";

export type BriefStatus =
  | "pending"
  | "generating"
  | "ready"
  | "approved"
  | "rejected"
  | "expired";

export type EditorialBrief = {
  id: string;
  tenant_id: string;
  story_cluster_id: string;
  brand_profile_id: string | null;
  status: BriefStatus;
  headline: string;
  angle: string;
  talking_points: string[];
  recommended_format: string;
  target_platforms: string[];
  tone_guidance: string;
  content_vertical: string;
  risk_notes: string;
  risk_level: string;
  operator_note: string | null;
  actioned_at: string | null;
  expires_at: string | null;
  created_at: string;
  updated_at: string;
};

export function getBriefs(status?: BriefStatus, init?: ApiFetchOptions) {
  const qs = status ? `?status=${encodeURIComponent(status)}` : "";
  return apiFetch<EditorialBrief[]>(`/briefs${qs}`, init);
}

export function getBrief(id: string) {
  return apiFetch<EditorialBrief>(`/briefs/${id}`);
}

export function generateBrief(payload: { story_cluster_id: string; brand_profile_id?: string; ttl_hours?: number }) {
  return apiFetch<EditorialBrief>("/briefs", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function approveBrief(id: string, operator_note?: string) {
  return apiFetch<EditorialBrief>(`/briefs/${id}/approve`, {
    method: "POST",
    body: JSON.stringify({ operator_note: operator_note ?? null }),
  });
}

export function rejectBrief(id: string, operator_note: string) {
  return apiFetch<EditorialBrief>(`/briefs/${id}/reject`, {
    method: "POST",
    body: JSON.stringify({ operator_note }),
  });
}

export function regenerateBrief(id: string) {
  return apiFetch<EditorialBrief>(`/briefs/${id}/regenerate`, {
    method: "POST",
  });
}

export type BriefRewritePayload = {
  mode?: string;
  operator_note?: string | null;
  requested_tone?: string | null;
  platform_mix?: string[] | null;
  content_format?: string | null;
};

export function rewriteBrief(id: string, payload: BriefRewritePayload = {}) {
  return apiFetch<EditorialBrief>(`/briefs/${id}/rewrite`, {
    method: "POST",
    body: JSON.stringify({
      mode: payload.mode ?? "rewrite",
      operator_note: payload.operator_note ?? null,
      requested_tone: payload.requested_tone ?? null,
      platform_mix: payload.platform_mix ?? null,
      content_format: payload.content_format ?? null,
    }),
  });
}

export function sendBriefToTelegram(id: string) {
  return apiFetch<{ ok?: boolean; message?: string }>(`/briefs/${id}/send-telegram`, {
    method: "POST",
  });
}
