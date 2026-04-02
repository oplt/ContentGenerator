import { apiFetch } from "./client";

export type AuthUser = {
    id: string;
    email: string;
    full_name: string | null;
    is_verified: boolean;
    is_admin: boolean;
    mfa_enabled: boolean;
};

export type AuthResponse = {
    access_token: string;
    token_type: string;
    user: AuthUser;
};

export async function signUp(payload: {
    email: string;
    password: string;
    full_name?: string;
    admin_invite_code?: string;
}) {
    return apiFetch("/auth/sign-up", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function signIn(payload: {
    email: string;
    password: string;
}): Promise<AuthResponse> {
    return apiFetch("/auth/sign-in", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function refresh(): Promise<AuthResponse> {
    return apiFetch("/auth/refresh", {
        method: "POST",
    });
}

export async function me() {
    return apiFetch("/auth/me");
}

export async function logout() {
    return apiFetch("/auth/logout", {
        method: "POST",
    });
}

export async function forgotPassword(payload: { email: string }) {
    return apiFetch("/auth/forgot-password", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function resetPassword(payload: { token: string; new_password: string }) {
    return apiFetch("/auth/reset-password", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function verifyEmail(payload: { token: string }) {
    return apiFetch("/auth/verify-email", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}

export async function resendVerification(payload: { email: string }) {
    return apiFetch("/auth/resend-verification", {
        method: "POST",
        body: JSON.stringify(payload),
    });
}
