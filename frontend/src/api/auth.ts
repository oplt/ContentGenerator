import { apiFetch } from "./client";

export type Membership = {
  tenant_id: string;
  tenant_name: string;
  tenant_slug: string;
  status: string;
  role?: {
    id: string | null;
    name: string | null;
    slug: string | null;
    permission_codes: string[];
  } | null;
};

export type AuthUser = {
  id: string;
  email: string;
  full_name: string | null;
  is_verified: boolean;
  is_admin: boolean;
  mfa_enabled: boolean;
  default_tenant_id: string | null;
  rbac_mode: string;
  memberships: Membership[];
};

export type AuthResponse = {
  user?: AuthUser | null;
  requires_email_verification?: boolean;
  message?: string | null;
};

export function signUp(payload: {
  email: string;
  password: string;
  full_name?: string;
  admin_invite_code?: string;
}) {
  return apiFetch<AuthResponse>("/auth/sign-up", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function signIn(payload: { email: string; password: string; mfa_code?: string }) {
  return apiFetch<AuthResponse>("/auth/sign-in", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function refresh() {
  return apiFetch<AuthResponse>("/auth/refresh", {
    method: "POST",
  });
}

export function me() {
  return apiFetch<AuthUser>("/auth/me");
}

export function logout() {
  return apiFetch<void>("/auth/logout", {
    method: "POST",
  });
}

export function verifyEmail(payload: { token: string }) {
  return apiFetch<void>("/auth/verify-email", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function forgotPassword(payload: { email: string }) {
  return apiFetch<void>("/auth/forgot-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function resetPassword(payload: { token: string; new_password: string }) {
  return apiFetch<void>("/auth/reset-password", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}
