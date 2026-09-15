import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import {
  ApiRequestError,
  apiFetch,
  isCurrentGeneration,
  nextRequestGeneration,
} from "../api/client";
import {
  approvalsNeedPolling,
  briefsNeedPolling,
  contentJobNeedsPolling,
  contentJobsNeedPolling,
  hasActiveStatuses,
  isDocumentVisible,
  publishingJobsNeedPolling,
  statusAwareRefetchInterval,
  TERMINAL_CONTENT_JOB_STATUSES,
} from "../lib/polling";

describe("polling policy", () => {
  it("treats empty collections as inactive", () => {
    expect(contentJobsNeedPolling([])).toBe(false);
    expect(publishingJobsNeedPolling(undefined)).toBe(false);
    expect(approvalsNeedPolling([])).toBe(false);
    expect(briefsNeedPolling([])).toBe(false);
  });

  it("keeps polling while non-terminal work exists", () => {
    expect(contentJobsNeedPolling([{ status: "processing" }, { status: "completed" }])).toBe(true);
    expect(contentJobsNeedPolling([{ status: "completed" }, { status: "failed" }])).toBe(false);
    expect(publishingJobsNeedPolling([{ status: "claimed" }])).toBe(true);
    expect(publishingJobsNeedPolling([{ status: "succeeded" }])).toBe(false);
    expect(approvalsNeedPolling([{ status: "pending" }])).toBe(true);
    expect(approvalsNeedPolling([{ status: "approved" }])).toBe(false);
    expect(briefsNeedPolling([{ status: "generating" }])).toBe(true);
    expect(briefsNeedPolling([{ status: "ready" }])).toBe(false);
    expect(contentJobNeedsPolling({ status: "queued" })).toBe(true);
    expect(contentJobNeedsPolling({ status: "completed" })).toBe(false);
  });

  it("pauses status-aware intervals when the document is hidden or idle", () => {
    const interval = statusAwareRefetchInterval(10_000, contentJobsNeedPolling);
    const original = Object.getOwnPropertyDescriptor(Document.prototype, "visibilityState");
    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "hidden",
    });
    expect(interval({ state: { data: [{ status: "processing" }] } } as never)).toBe(false);

    Object.defineProperty(document, "visibilityState", {
      configurable: true,
      get: () => "visible",
    });
    expect(isDocumentVisible()).toBe(true);
    expect(interval({ state: { data: [{ status: "completed" }] } } as never)).toBe(false);
    expect(interval({ state: { data: [{ status: "processing" }] } } as never)).toBe(10_000);
    expect(hasActiveStatuses([{ status: "RUNNING" }], TERMINAL_CONTENT_JOB_STATUSES)).toBe(true);

    if (original) {
      Object.defineProperty(document, "visibilityState", original);
    } else {
      Reflect.deleteProperty(document, "visibilityState");
    }
  });
});

describe("apiFetch bounds", () => {
  const originalFetch = globalThis.fetch;

  beforeEach(() => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_input: RequestInfo | URL, init?: RequestInit) => {
        await new Promise<void>((resolve, reject) => {
          const timer = window.setTimeout(resolve, 50);
          init?.signal?.addEventListener(
            "abort",
            () => {
              window.clearTimeout(timer);
              reject(new DOMException("Aborted", "AbortError"));
            },
            { once: true }
          );
        });
        return new Response(JSON.stringify({ ok: true }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      })
    );
  });

  afterEach(() => {
    globalThis.fetch = originalFetch;
    vi.unstubAllGlobals();
  });

  it("times out and marks the error retryable", async () => {
    await expect(apiFetch("/health/ready", { timeoutMs: 5 })).rejects.toMatchObject({
      name: "ApiRequestError",
      code: "timeout",
      retryable: true,
    } satisfies Partial<ApiRequestError>);
  });

  it("respects caller abort without reporting a timeout", async () => {
    const controller = new AbortController();
    const pending = apiFetch("/health/ready", { signal: controller.signal, timeoutMs: 1_000 });
    controller.abort();
    await expect(pending).rejects.toMatchObject({
      code: "aborted",
      retryable: false,
    });
  });

  it("tracks request generations so stale work can be ignored", () => {
    const first = nextRequestGeneration();
    const second = nextRequestGeneration();
    expect(isCurrentGeneration(first)).toBe(false);
    expect(isCurrentGeneration(second)).toBe(true);
  });
});
