import { initWebVitals } from "./webVitals";

describe("web vitals registration", () => {
  it("registers observers once even when initialized repeatedly", () => {
    const observe = vi.fn();
    let constructed = 0;
    class MockPerformanceObserver {
      constructor(callback: PerformanceObserverCallback) {
        void callback;
        constructed += 1;
      }

      observe = observe;
    }

    vi.stubGlobal("PerformanceObserver", MockPerformanceObserver);
    initWebVitals();
    initWebVitals();

    expect(constructed).toBe(3);
    expect(observe).toHaveBeenCalledTimes(3);
    vi.unstubAllGlobals();
  });
});
