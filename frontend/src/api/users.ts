import { apiFetch } from "./client";

export type UserProfile = {
  id: string;
  email: string;
  full_name: string | null;
  is_verified: boolean;
  mfa_enabled: boolean;
};

export type UserSession = {
  id: string;
  created_at: string;
  expires_at: string;
};

export function getMyProfile() {
  return apiFetch<UserProfile>("/users/me");
}

export function updateMyProfile(payload: { full_name?: string | null }) {
  return apiFetch<UserProfile>("/users/me", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function changeMyPassword(payload: { current_password: string; new_password: string }) {
  return apiFetch<void>("/users/me/password", {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function listMySessions() {
  return apiFetch<UserSession[]>("/users/me/sessions");
}

export function revokeMySession(sessionId: string) {
  return apiFetch<void>(`/users/me/sessions/${sessionId}`, {
    method: "DELETE",
  });
}
