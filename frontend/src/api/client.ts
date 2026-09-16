import { getCsrfToken, persistCsrfToken } from "../features/auth/csrf";
import { useWorkspaceStore } from "../store/workspaceStore";

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

let refreshPromise: Promise<unknown | null> | null = null;

/** Monotonic counter so callers can detect superseded in-flight responses. */
let requestGeneration = 0;

export type ApiErrorCode = "timeout" | "aborted" | "http" | "network";

export class ApiRequestError extends Error {
  readonly code: ApiErrorCode;
  readonly retryable: boolean;
  readonly status?: number;
  readonly details?: unknown;

  constructor(
    message: string,
    code: ApiErrorCode,
    options?: { retryable?: boolean; status?: number; cause?: unknown; details?: unknown }
  ) {
    super(message, options?.cause ? { cause: options.cause } : undefined);
    this.name = "ApiRequestError";
    this.code = code;
    this.retryable = options?.retryable ?? (code === "timeout" || code === "network");
    this.status = options?.status;
    this.details = options?.details;
  }
}

export type ApiFetchOptions = RequestInit & {
  /** Soft deadline for the HTTP round-trip. Defaults to 30s. Set 0 to disable. */
  timeoutMs?: number;
};

function getCookie(name: string): string | null {
  if (name === "csrf_token") {
    return getCsrfToken();
  }
  if (typeof document === "undefined" || typeof document.cookie !== "string") {
    return null;
  }
  const match = document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${name}=`));
  return match ? decodeURIComponent(match.split("=")[1] ?? "") : null;
}

function composeAbortSignal(signals: AbortSignal[]): AbortSignal {
  if (signals.length === 1) {
    return signals[0];
  }
  const AbortSignalAny = (AbortSignal as typeof AbortSignal & {
    any?: (input: AbortSignal[]) => AbortSignal;
  }).any;
  if (typeof AbortSignalAny === "function") {
    return AbortSignalAny(signals);
  }
  const controller = new AbortController();
  const onAbort = () => {
    controller.abort();
    for (const signal of signals) {
      signal.removeEventListener("abort", onAbort);
    }
  };
  for (const signal of signals) {
    if (signal.aborted) {
      controller.abort();
      break;
    }
    signal.addEventListener("abort", onAbort, { once: true });
  }
  return controller.signal;
}

function createTimeoutSignal(timeoutMs: number): { signal: AbortSignal; clear: () => void } {
  const controller = new AbortController();
  const timer = window.setTimeout(() => {
    controller.abort();
  }, timeoutMs);
  return {
    signal: controller.signal,
    clear: () => window.clearTimeout(timer),
  };
}

async function performRefresh(): Promise<unknown | null> {
  try {
    const response = await fetch(`${API_BASE}/auth/refresh`, {
      method: "POST",
      credentials: "include",
      headers: getCsrfToken() ? { "X-CSRF-Token": getCsrfToken() as string } : undefined,
    });
    if (!response.ok) {
      return null;
    }
    const payload = await response.json().catch(() => null) as { csrf_token?: string } | null;
    persistCsrfToken(payload?.csrf_token, true);
    return payload;
  } catch {
    return null;
  }
}

/** Share one refresh request between auth bootstrap and 401 retries. */
export function refreshSession<T>(): Promise<T | null> {
  if (!refreshPromise) {
    refreshPromise = performRefresh().finally(() => {
      refreshPromise = null;
    });
  }
  return refreshPromise as Promise<T | null>;
}

function toApiError(error: unknown, timedOut: boolean): ApiRequestError {
  if (error instanceof ApiRequestError) {
    return error;
  }
  if (timedOut) {
    return new ApiRequestError("Request timed out. Retry when ready.", "timeout", {
      retryable: true,
      cause: error,
    });
  }
  if (
    (error instanceof DOMException && error.name === "AbortError") ||
    (error instanceof Error && error.name === "AbortError")
  ) {
    return new ApiRequestError("Request was cancelled.", "aborted", {
      retryable: false,
      cause: error,
    });
  }
  return new ApiRequestError(
    error instanceof Error ? error.message : "Network request failed.",
    "network",
    { retryable: true, cause: error }
  );
}

export function nextRequestGeneration(): number {
  requestGeneration += 1;
  return requestGeneration;
}

export function isCurrentGeneration(generation: number): boolean {
  return generation === requestGeneration;
}

export async function apiFetch<T>(
  path: string,
  options: ApiFetchOptions = {},
  retry = true
): Promise<T> {
  const { timeoutMs = 30_000, signal: userSignal, ...requestInit } = options;
  const headers = new Headers(requestInit.headers ?? {});
  const isFormData = requestInit.body instanceof FormData;
  if (!isFormData && requestInit.body !== undefined && !headers.has("Content-Type")) {
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

  const signals: AbortSignal[] = [];
  if (userSignal) {
    signals.push(userSignal);
  }
  const timeout = timeoutMs > 0 ? createTimeoutSignal(timeoutMs) : null;
  if (timeout) {
    signals.push(timeout.signal);
  }
  const signal = signals.length > 0 ? composeAbortSignal(signals) : undefined;
  let timedOut = false;
  if (timeout) {
    const markTimeout = () => {
      timedOut = true;
    };
    timeout.signal.addEventListener("abort", markTimeout, { once: true });
  }

  try {
    const response = await fetch(`${API_BASE}${path}`, {
      ...requestInit,
      headers,
      credentials: "include",
      signal,
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
      const refreshed = await refreshSession<{ csrf_token?: string }>();
      if (!refreshed) {
        throw new ApiRequestError("Session expired. Please sign in again.", "http", {
          retryable: false,
          status: 401,
        });
      }
      return apiFetch<T>(path, options, false);
    }

    if (!response.ok) {
      const error = await response
        .json()
        .catch(() => ({ error: { message: "Request failed" } }));
      const details = error.error?.details ?? error.detail ?? undefined;
      let message =
        error.error?.message ??
        error.detail ??
        error.message ??
        "Request failed";
      if (Array.isArray(details) && details.length > 0) {
        const first = details[0] as { msg?: string; loc?: unknown[] };
        const loc = Array.isArray(first.loc) ? first.loc.join(".") : "";
        const detailMsg = first.msg ? `${loc ? `${loc}: ` : ""}${first.msg}` : "";
        if (detailMsg) {
          message = `${message} (${detailMsg})`;
        }
      }
      const transient =
        response.status === 429 ||
        response.status === 502 ||
        response.status === 503 ||
        response.status === 504;
      throw new ApiRequestError(String(message), "http", {
        // Do not treat every 5xx as retryable (deterministic 500s stay fail-fast).
        retryable: transient,
        status: response.status,
        details,
      });
    }

    if (response.status === 204) {
      return undefined as T;
    }

    return response.json() as Promise<T>;
  } catch (error) {
    const apiError = toApiError(
      error,
      timedOut || Boolean(timeout?.signal.aborted && !userSignal?.aborted)
    );
    // One short retry for transient connect failures (e.g. Vite up before API).
    if (retry && apiError.retryable && apiError.code === "network") {
      await new Promise((resolve) => window.setTimeout(resolve, 250));
      return apiFetch<T>(path, options, false);
    }
    throw apiError;
  } finally {
    timeout?.clear();
  }
}
