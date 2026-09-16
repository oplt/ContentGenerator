import { ApiRequestError } from "../api/client";

/** HTTP statuses safe to auto-retry (transient). */
export const TRANSIENT_HTTP_STATUSES = new Set([429, 502, 503, 504]);

const MAX_QUERY_RETRIES = 2;

export function isTransientHttpStatus(status: number | undefined): boolean {
  return typeof status === "number" && TRANSIENT_HTTP_STATUSES.has(status);
}

/**
 * Query auto-retry: only transient network/timeout and selected HTTP statuses.
 * Never retries deterministic 4xx (except 429) or mutations (handled separately).
 */
export function shouldRetryQuery(failureCount: number, error: unknown): boolean {
  if (failureCount >= MAX_QUERY_RETRIES) {
    return false;
  }
  if (error instanceof ApiRequestError) {
    if (error.code === "aborted") {
      return false;
    }
    if (error.status !== undefined) {
      if (error.status >= 400 && error.status < 500 && error.status !== 429) {
        return false;
      }
      if (error.status >= 500 && !isTransientHttpStatus(error.status)) {
        return false;
      }
    }
    return error.retryable || isTransientHttpStatus(error.status);
  }
  if (error instanceof Error && "retryable" in error) {
    return (error as { retryable?: boolean }).retryable !== false;
  }
  return failureCount < 1;
}
