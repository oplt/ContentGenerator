import { apiFetch } from "./client";

export type SocialAccount = {
  id: string;
  platform: string;
  display_name: string;
  handle: string | null;
  account_external_id: string | null;
  status: string;
  capability_flags: Record<string, string>;
  metadata: Record<string, string>;
};

export type SocialAccountUpsertPayload = {
  platform: string;
  display_name: string;
  handle?: string | null;
  account_external_id?: string | null;
  access_token?: string | null;
  refresh_token?: string | null;
  scopes?: string[];
  metadata?: Record<string, string>;
  use_stub?: boolean;
};

export type PublishingJob = {
  id: string;
  content_job_id: string;
  social_account_id: string | null;
  approval_request_id: string | null;
  platform: string;
  status: string;
  provider: string;
  idempotency_key: string;
  dry_run: boolean;
  scheduled_for: string | null;
  published_at: string | null;
  retry_count: number;
  failure_reason: string | null;
  external_post_id: string | null;
  external_post_url: string | null;
  provider_payload: Record<string, string>;
};

export type PublishedPost = {
  id: string;
  platform: string;
  post_type: string;
  external_post_id: string | null;
  external_url: string | null;
  status: string;
  published_at: string | null;
};

export function getSocialAccounts() {
  return apiFetch<SocialAccount[]>("/publishing/social-accounts");
}

export function upsertSocialAccount(payload: SocialAccountUpsertPayload) {
  return apiFetch<SocialAccount>("/publishing/social-accounts", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getPublishingJobs() {
  return apiFetch<PublishingJob[]>("/publishing/queue");
}

export function publishNow(payload: Record<string, unknown>) {
  return apiFetch<PublishingJob[]>("/publishing/publish-now", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function getPublishedPosts() {
  return apiFetch<PublishedPost[]>("/publishing/posts");
}
