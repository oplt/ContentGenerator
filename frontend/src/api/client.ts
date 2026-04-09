import { useWorkspaceStore } from "../store/workspaceStore";

const API_BASE = import.meta.env.VITE_API_BASE ?? "http://localhost:8000/api/v1";

let refreshPromise: Promise<boolean> | null = null;

function getCookie(name: string): string | null {
  const match = document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1] ?? "") : null;
}

async function refreshAccessToken(): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: getCookie("csrf_token") ? { "X-CSRF-Token": getCookie("csrf_token") as string } : undefined,
    });
    return response.ok;
  } catch {
    return false;
  }
}

export async function apiFetch<T>(path: string, options: RequestInit = {}, retry = true): Promise<T> {
  const headers = new Headers(options.headers ?? {});
  const isFormData = options.body instanceof FormData;
  if (!isFormData && options.body !== undefined && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const tenantId = useWorkspaceStore.getState().tenantId;
  if (tenantId) {
    headers.set("X-Tenant-ID", tenantId);
  }
  const csrfToken = getCookie("csrf_token");
  if (csrfToken) {
    headers.set("X-CSRF-Token", csrfToken);
  }

  const response = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers,
    credentials: "include",
  });

  const canRetryWithRefresh =
    retry &&
    response.status === 401 &&
    ![
      "/auth/sign-in",
      "/auth/sign-up",
      "/auth/forgot-password",
      "/auth/reset-password",
      "/auth/verify-email",
      "/auth/refresh",
    ].includes(path);

  if (canRetryWithRefresh) {
    if (!refreshPromise) {
      refreshPromise = refreshAccessToken().finally(() => {
        refreshPromise = null;
      });
    }
    const refreshed = await refreshPromise;
    if (!refreshed) {
      throw new Error("Session expired. Please sign in again.");
    }
    return apiFetch<T>(path, options, false);
  }

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ error: { message: "Request failed" } }));
    throw new Error(error.error?.message ?? "Request failed");
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
