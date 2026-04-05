import { apiFetch } from "./client";

export type ApprovalMessage = {
  id: string;
  direction: string;
  channel: string;
  provider_message_id: string | null;
  message_type: string;
  raw_text: string | null;
  parsed_intent: string;
  intent_confidence: number;
  user_feedback: string | null;
  payload: Record<string, string>;
};

export type ApprovalRequest = {
  id: string;
  content_job_id: string;
  status: string;
  channel: string;
  recipient: string;
  provider: string;
  provider_request_id: string | null;
  requested_at: string | null;
  responded_at: string | null;
  revision_count: number;
  expires_at: string | null;
  last_sent_at: string | null;
  messages: ApprovalMessage[];
};

export function getApprovalRequests() {
  return apiFetch<ApprovalRequest[]>("/approvals");
}

export function sendApprovalRequest(payload: { content_job_id: string; recipient?: string | null }) {
  return apiFetch<ApprovalRequest>("/approvals", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
