/**
 * Lightweight Web Vitals reporter (T8.1).
 * Uses PerformanceObserver — no extra npm dependency.
 * Beacons to POST /health/web-vitals (public, low-cardinality).
 */

const API_BASE = import.meta.env.VITE_API_BASE ?? "/api/v1";

type VitalName = "lcp" | "cls" | "inp" | "fcp" | "ttfb";

let initialized = false;

function ratingFor(name: VitalName, value: number): string {
  // Thresholds aligned with docs/benchmarks/baseline.json (p95 budgets).
  if (name === "lcp") return value <= 2500 ? "good" : value <= 4000 ? "needs-improvement" : "poor";
  if (name === "cls") return value <= 0.1 ? "good" : value <= 0.25 ? "needs-improvement" : "poor";
  if (name === "inp") return value <= 200 ? "good" : value <= 500 ? "needs-improvement" : "poor";
  if (name === "fcp") return value <= 1800 ? "good" : value <= 3000 ? "needs-improvement" : "poor";
  return value <= 800 ? "good" : value <= 1800 ? "needs-improvement" : "poor";
}

function navigationType(): string {
  try {
    const entry = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
    return (entry?.type as string | undefined) ?? "unknown";
  } catch {
    return "unknown";
  }
}

function send(name: VitalName, value: number): void {
  const body = JSON.stringify({
    name,
    value,
    rating: ratingFor(name, value),
    navigation_type: navigationType(),
  });
  const url = `${API_BASE}/health/web-vitals`;
  try {
    if (typeof navigator !== "undefined" && typeof navigator.sendBeacon === "function") {
      const blob = new Blob([body], { type: "application/json" });
      if (navigator.sendBeacon(url, blob)) return;
    }
    void fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
      credentials: "omit",
    });
  } catch {
    // Best-effort telemetry; never break the app shell.
  }
}

function observeLcp(): void {
  try {
    const po = new PerformanceObserver((list) => {
      const entries = list.getEntries();
      const last = entries[entries.length - 1] as PerformanceEntry & { startTime?: number };
      if (last?.startTime != null) send("lcp", last.startTime);
    });
    po.observe({ type: "largest-contentful-paint", buffered: true } as PerformanceObserverInit);
  } catch {
    /* unsupported */
  }
}

function observeCls(): void {
  try {
    let cls = 0;
    const po = new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as Array<PerformanceEntry & { hadRecentInput?: boolean; value?: number }>) {
        if (!entry.hadRecentInput && typeof entry.value === "number") {
          cls += entry.value;
        }
      }
      send("cls", cls);
    });
    po.observe({ type: "layout-shift", buffered: true } as PerformanceObserverInit);
  } catch {
    /* unsupported */
  }
}

function observeInp(): void {
  try {
    let maxDuration = 0;
    const po = new PerformanceObserver((list) => {
      for (const entry of list.getEntries() as Array<PerformanceEntry & { duration?: number; interactionId?: number }>) {
        if (entry.interactionId && typeof entry.duration === "number" && entry.duration > maxDuration) {
          maxDuration = entry.duration;
          send("inp", maxDuration);
        }
      }
    });
    po.observe({ type: "event", buffered: true, durationThreshold: 16 } as PerformanceObserverInit);
  } catch {
    /* unsupported */
  }
}

function observePaintAndTtfb(): void {
  try {
    const paints = performance.getEntriesByType("paint");
    for (const entry of paints) {
      if (entry.name === "first-contentful-paint") send("fcp", entry.startTime);
    }
    const nav = performance.getEntriesByType("navigation")[0] as PerformanceNavigationTiming | undefined;
    if (nav && nav.responseStart > 0) {
      send("ttfb", nav.responseStart);
    }
  } catch {
    /* unsupported */
  }
}

/** Start observers once per page load. Safe to call from main.tsx. */
export function initWebVitals(): void {
  if (typeof window === "undefined" || typeof PerformanceObserver === "undefined") return;
  if (initialized) return;
  initialized = true;
  observeLcp();
  observeCls();
  observeInp();
  observePaintAndTtfb();
}
