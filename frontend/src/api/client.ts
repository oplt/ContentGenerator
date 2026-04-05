import { authStore } from "../features/auth/store/authStore";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1";

let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
    try {
        const res = await fetch(`${API_BASE}/auth/refresh`, {
            method: "POST",
            credentials: "include",
        });
        if (!res.ok) return null;
        const data = await res.json();
        authStore.setAccessToken(data.access_token ?? null);
        return data.access_token ?? null;
    } catch {
        return null;
    }
}

export async function apiFetch<T>(
    path: string,
    options: RequestInit = {},
    retry = true
): Promise<T> {
    const headers = new Headers(options.headers ?? {});
    const isFormData = options.body instanceof FormData;

    if (!isFormData && options.body !== undefined && !headers.has("Content-Type")) {
        headers.set("Content-Type", "application/json");
    }

    if (authStore.accessToken) {
        headers.set("Authorization", `Bearer ${authStore.accessToken}`);
    }

    const response = await fetch(`${API_BASE}${path}`, {
        ...options,
        headers,
        credentials: "include",
    });

    if (response.status === 401 && retry) {
        // Deduplicate concurrent refresh attempts
        if (!refreshPromise) {
            refreshPromise = refreshAccessToken().finally(() => {
                refreshPromise = null;
            });
        }
        const newToken = await refreshPromise;
        if (!newToken) {
            throw new Error("Session expired. Please sign in again.");
        }
        return apiFetch<T>(path, options, false);
    }

    if (!response.ok) {
        const error = await response.json().catch(() => ({ detail: "Request failed" }));
        throw new Error(error.detail ?? "Request failed");
    }

    // Handle 204 No Content
    if (response.status === 204) return undefined as T;

    return response.json();
}
