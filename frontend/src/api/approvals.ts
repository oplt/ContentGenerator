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
  content_job_id: string | null;
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
  related_entity_type: string | null;
  related_entity_id: string | null;
  approval_type: string;
  buttons_json: string[];
  telegram_message_id: string | null;
  callback_verification_failures: number;
  callback_last_error: string | null;
  responded_by: string | null;
  risk_label: string | null;
  response_payload_json: Record<string, unknown>;
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

export function resendApprovalRequest(requestId: string) {
  return apiFetch<ApprovalRequest>(`/approvals/${requestId}/resend`, {
    method: "POST",
  });
}

export function actionApprovalRequest(
  requestId: string,
  payload: { action: string; feedback?: string | null }
) {
  return apiFetch<ApprovalRequest>(`/approvals/${requestId}/action`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
