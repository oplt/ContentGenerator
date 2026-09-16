import { describe, expect, it } from "vitest";
import {
  approvalRequestId,
  formatDurationMs,
  publishingJobIds,
} from "./runInspection";
import type { WorkflowNodeRun } from "../../api/workflows";

function node(partial: Partial<WorkflowNodeRun>): WorkflowNodeRun {
  return {
    id: "nr-1",
    workflow_run_id: "run-1",
    node_id: "n1",
    node_type: "publish",
    node_version: 1,
    status: "succeeded",
    attempt: 1,
    input_json: {},
    output_json: {},
    error_json: null,
    waiting_reason: null,
    resume_token: null,
    started_at: null,
    finished_at: null,
    ...partial,
  };
}

describe("runInspection", () => {
  it("formats durations", () => {
    expect(formatDurationMs(null)).toBe("—");
    expect(formatDurationMs(420)).toBe("420ms");
    expect(formatDurationMs(1500)).toBe("1.5s");
  });

  it("extracts approval and publishing links", () => {
    expect(
      approvalRequestId(node({ output_json: { approval_request_id: "appr-1" } })),
    ).toBe("appr-1");
    expect(publishingJobIds(node({ output_json: { job_ids: ["j1", 2, "j2"] } }))).toEqual([
      "j1",
      "j2",
    ]);
  });
});
