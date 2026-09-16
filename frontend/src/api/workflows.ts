/** Workflow + automation API client (Phase 13). */

import { apiFetch, type ApiFetchOptions } from "./client";
import type {
  Automation,
  BrandOption,
  CompileContextPayload,
  NodeTestResult,
  WorkflowCompileResult,
  WorkflowDefinition,
  WorkflowGraph,
  WorkflowNodeDefinition,
  WorkflowRun,
  WorkflowRunDetail,
  WorkflowVersion,
} from "./workflowTypes";

export * from "./workflowTypes";

export function listWorkflowDefinitions(init?: ApiFetchOptions) {
  return apiFetch<WorkflowDefinition[]>("/workflows/definitions", init);
}

export function getWorkflowDefinition(definitionId: string, init?: ApiFetchOptions) {
  return apiFetch<WorkflowDefinition>(`/workflows/definitions/${definitionId}`, init);
}

export function createWorkflowDefinition(payload: {
  name: string;
  slug: string;
  description?: string | null;
}) {
  return apiFetch<WorkflowDefinition>("/workflows/definitions", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listWorkflowVersions(definitionId: string, init?: ApiFetchOptions) {
  return apiFetch<WorkflowVersion[]>(`/workflows/definitions/${definitionId}/versions`, init);
}

export function saveWorkflowDraft(
  definitionId: string,
  payload: {
    graph: WorkflowGraph;
    input_schema_json?: Record<string, unknown>;
    output_schema_json?: Record<string, unknown>;
  },
) {
  return apiFetch<WorkflowVersion>(`/workflows/definitions/${definitionId}/draft`, {
    method: "PUT",
    body: JSON.stringify(payload),
  });
}

export function validateWorkflowGraph(payload: {
  graph: WorkflowGraph;
  context?: CompileContextPayload | null;
}) {
  return apiFetch<WorkflowCompileResult>("/workflows/validate-graph", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function publishWorkflowVersion(
  definitionId: string,
  payload?: { version_id?: string | null; context?: CompileContextPayload | null },
) {
  return apiFetch<WorkflowVersion>(`/workflows/definitions/${definitionId}/publish`, {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
}

export function startWorkflowRun(
  definitionId: string,
  payload?: {
    workflow_version_id?: string | null;
    brand_id?: string | null;
    trigger_payload?: Record<string, unknown>;
    initial_inputs?: Record<string, unknown>;
    context?: CompileContextPayload | null;
    advance?: boolean;
    run_config?: Record<string, unknown>;
    dry_run?: boolean;
    mock_generation?: boolean;
    simulate_approval?: boolean;
  },
) {
  return apiFetch<WorkflowRunDetail>(`/workflows/definitions/${definitionId}/runs`, {
    method: "POST",
    body: JSON.stringify(payload ?? {}),
  });
}

export function testWorkflowNode(
  nodeType: string,
  payload: {
    version?: number | null;
    config?: Record<string, unknown>;
    inputs?: Record<string, unknown>;
    dry_run?: boolean;
    mock_generation?: boolean;
    brand_id?: string | null;
    context?: CompileContextPayload | null;
  },
) {
  return apiFetch<NodeTestResult>(`/workflows/nodes/${encodeURIComponent(nodeType)}/test`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listWorkflowRuns(
  params?: { status?: string; limit?: number },
  init?: ApiFetchOptions,
) {
  const search = new URLSearchParams();
  if (params?.status) search.set("status", params.status);
  if (params?.limit) search.set("limit", String(params.limit));
  const qs = search.toString();
  return apiFetch<WorkflowRun[]>(`/workflows/runs${qs ? `?${qs}` : ""}`, init);
}

export function getWorkflowRun(runId: string, init?: ApiFetchOptions) {
  return apiFetch<WorkflowRunDetail>(`/workflows/runs/${runId}`, init);
}

export function advanceWorkflowRun(runId: string) {
  return apiFetch<WorkflowRunDetail>(`/workflows/runs/${runId}/advance`, { method: "POST" });
}

export function resumeWorkflowRun(payload: {
  resume_token: string;
  outcome: string;
  decision?: Record<string, unknown>;
  advance?: boolean;
}) {
  return apiFetch<WorkflowRunDetail>("/workflows/resume", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function listWorkflowNodes(init?: ApiFetchOptions) {
  return apiFetch<WorkflowNodeDefinition[]>("/workflows/nodes", init);
}

export function listAutomations(init?: ApiFetchOptions) {
  return apiFetch<Automation[]>("/workflows/automations", init);
}

export function createAutomation(payload: {
  name: string;
  workflow_definition_id: string;
  workflow_version_id?: string | null;
  brand_id?: string | null;
  enabled?: boolean;
  trigger_type?: string;
  trigger_config?: Record<string, unknown>;
  timezone?: string;
  social_account_ids?: string[];
  settings?: Record<string, unknown>;
}) {
  return apiFetch<Automation>("/workflows/automations", {
    method: "POST",
    body: JSON.stringify(payload),
  });
}

export function updateAutomation(
  automationId: string,
  payload: {
    name?: string;
    enabled?: boolean;
    workflow_version_id?: string | null;
    trigger_type?: string;
    trigger_config?: Record<string, unknown>;
    timezone?: string;
    social_account_ids?: string[] | null;
    settings?: Record<string, unknown>;
  },
) {
  return apiFetch<Automation>(`/workflows/automations/${automationId}`, {
    method: "PATCH",
    body: JSON.stringify(payload),
  });
}

export function listWorkflowBrands(init?: ApiFetchOptions) {
  return apiFetch<BrandOption[]>("/workflows/brands", init);
}
