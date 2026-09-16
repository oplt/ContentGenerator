import { ApiRequestError } from "../api/client";
import { isTransientHttpStatus, shouldRetryQuery } from "./queryRetry";

describe("queryRetry", () => {
  it("treats only selected HTTP statuses as transient", () => {
    expect(isTransientHttpStatus(429)).toBe(true);
    expect(isTransientHttpStatus(502)).toBe(true);
    expect(isTransientHttpStatus(500)).toBe(false);
    expect(isTransientHttpStatus(403)).toBe(false);
  });

  it("does not retry 400, 401, or 403", () => {
    for (const status of [400, 401, 403, 404, 422]) {
      const error = new ApiRequestError("client error", "http", {
        status,
        retryable: false,
      });
      expect(shouldRetryQuery(0, error)).toBe(false);
    }
  });

  it("retries transient HTTP and network errors within the cap", () => {
    const transient = new ApiRequestError("upstream", "http", {
      status: 503,
      retryable: true,
    });
    expect(shouldRetryQuery(0, transient)).toBe(true);
    expect(shouldRetryQuery(1, transient)).toBe(true);
    expect(shouldRetryQuery(2, transient)).toBe(false);
  });

  it("does not retry aborted requests", () => {
    const aborted = new ApiRequestError("aborted", "aborted", { retryable: false });
    expect(shouldRetryQuery(0, aborted)).toBe(false);
  });

  it("does not retry plain 500 responses", () => {
    const error = new ApiRequestError("server error", "http", {
      status: 500,
      retryable: false,
    });
    expect(shouldRetryQuery(0, error)).toBe(false);
  });
});
