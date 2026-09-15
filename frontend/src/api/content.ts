import { apiFetch, type ApiFetchOptions } from "./client";

export type BrandProfile = {
  id: string;
  name: string;
  niche: string;
  tone: string;
  audience: string;
  voice_notes: string | null;
  preferred_platforms: string[];
  default_cta: string | null;
  hashtags_strategy: string;
  risk_tolerance: string;
  require_whatsapp_approval: boolean;
  guardrails: Record<string, string>;
  visual_style: Record<string, string>;
};

export type ContentPlan = {
  id: string;
  story_cluster_id: string;
  brand_profile_id: string | null;
  status: string;
  decision: string;
  content_format: string;
  target_platforms: string[];
  target_social_account_ids?: string[];
  tone: string;
  urgency: string;
  risk_flags: string[];
  recommended_cta: string | null;
  hashtags_strategy: string;
  approval_required: boolean;
  safe_to_publish: boolean;
  policy_trace: Record<string, string>;
  scheduled_for: string | null;
};

export type ContentAsset = {
  id: string;
  asset_type: string;
  platform: string | null;
  variant_label: string | null;
  public_url: string | null;
  mime_type: string;
  metadata: Record<string, string>;
  source_trace: Record<string, string>;
  text_content: string | null;
  asset_group_id?: string | null;
};

export type ContentJob = {
  id: string;
  content_plan_id: string;
  revision_of_job_id: string | null;
  job_type: string;
  status: string;
  stage: string;
  progress: number;
  feedback: string | null;
  error_message: string | null;
  risk_label: string | null;
  risk_review: Record<string, unknown>;
  target_social_account_ids?: string[];
  variant_fingerprints?: Record<string, string[]>;
  asset_group_id?: string | null;
  started_at: string | null;
  completed_at: string | null;
  assets: ContentAsset[];
};

export function getBrandProfile() {
  return apiFetch<BrandProfile>("/content/brand-profile");
}

export function upsertBrandProfile(payload: Record<string, unknown>) {
  return apiFetch<BrandProfile>("/content/brand-profile", {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function getContentPlans() {
  return apiFetch<ContentPlan[]>("/content/plans");
}

export function createContentPlan(payload: { story_cluster_id: string; brand_profile_id?: string | null }) {
  return apiFetch<ContentPlan>("/content/plans", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getContentJobs(init?: ApiFetchOptions) {
  return apiFetch<ContentJob[]>("/content/jobs", init);
}

export function getContentJob(id: string, init?: ApiFetchOptions) {
  return apiFetch<ContentJob>(`/content/jobs/${id}`, init);
}

export function generateContent(payload: {
  content_plan_id: string;
  social_account_ids?: string[] | null;
}) {
  return apiFetch<ContentJob>("/content/generate", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function regenerateContent(jobId: string, feedback: string) {
  return apiFetch<ContentJob>(`/content/jobs/${jobId}/regenerate`, {
    method: "POST",
    body: JSON.stringify({ feedback }),
  });
}

export function regenerateAssetGroup(assetGroupId: string, instruction: string) {
  return apiFetch<ContentJob>(`/content/asset-groups/${assetGroupId}/regenerate`, {
    method: "POST",
    body: JSON.stringify({ instruction }),
  });
}
