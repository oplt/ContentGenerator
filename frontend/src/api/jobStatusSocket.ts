/**
 * Optional job WebSocket client (Phase 7.4).
 *
 * Prefer status-aware REST polling for content/publishing jobs until workers
 * reliably publish Redis `job_status_updates`. Use this helper as an opt-in
 * accelerator that invalidates job queries on message without replacing REST.
 */
import { queryClient } from "../lib/queryClient";
import { queryKeys } from "../lib/queryKeys";

function resolveWsBase(): string {
  if (import.meta.env.VITE_WS_BASE) {
    return import.meta.env.VITE_WS_BASE as string;
  }
  const apiBase = (import.meta.env.VITE_API_BASE as string | undefined) ?? "/api/v1";
  if (/^https?:\/\//i.test(apiBase)) {
    return apiBase.replace(/\/api\/v1\/?$/, "").replace(/^http/i, "ws");
  }
  if (typeof window !== "undefined") {
    const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
    return `${protocol}//${window.location.host}`;
  }
  return "ws://127.0.0.1:8000";
}

const WS_BASE = resolveWsBase();

export type JobStatusSocketHandlers = {
  onUpdate?: (payload: Record<string, unknown>) => void;
  onError?: (error: Event) => void;
};

export function connectJobStatusSocket(
  jobId: string,
  tenantId: string | null,
  handlers: JobStatusSocketHandlers = {}
): () => void {
  if (!jobId || typeof window === "undefined") {
    return () => undefined;
  }

  const url = `${WS_BASE.replace(/^http/, "ws")}/api/v1/ws/job/${encodeURIComponent(jobId)}`;
  let socket: WebSocket | null = null;
  let closed = false;
  let retries = 0;
  let retryTimer: number | null = null;

  const cleanupTimer = () => {
    if (retryTimer !== null) {
      window.clearTimeout(retryTimer);
      retryTimer = null;
    }
  };

  const open = () => {
    if (closed) {
      return;
    }
    socket = new WebSocket(url);
    socket.onmessage = (event) => {
      try {
        const payload = JSON.parse(String(event.data)) as Record<string, unknown>;
        handlers.onUpdate?.(payload);
        if (tenantId) {
          void queryClient.invalidateQueries({ queryKey: queryKeys.contentJob(tenantId, jobId) });
          void queryClient.invalidateQueries({ queryKey: queryKeys.contentJobs(tenantId) });
        }
      } catch {
        // Ignore malformed frames; REST polling remains the source of truth.
      }
    };
    socket.onerror = (event) => {
      handlers.onError?.(event);
    };
    socket.onclose = () => {
      if (closed) {
        return;
      }
      retries += 1;
      const delay = Math.min(30_000, 1_000 * 2 ** Math.min(retries, 4));
      cleanupTimer();
      retryTimer = window.setTimeout(open, delay);
    };
  };

  open();

  return () => {
    closed = true;
    cleanupTimer();
    socket?.close();
    socket = null;
  };
}
