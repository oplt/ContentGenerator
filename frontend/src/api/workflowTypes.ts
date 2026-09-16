/** Workflow API types (Phase 13). */

export type WorkflowDefinition = {
  id: string;
  tenant_id: string;
  name: string;
  slug: string;
  description: string | null;
  status: string;
  current_version_id: string | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkflowGraphNode = {
  id: string;
  type: string;
  version: number;
  config: Record<string, unknown>;
};

export type WorkflowGraphEdge = {
  source: string;
  target: string;
  condition?: string | null;
};

export type WorkflowGraph = {
  nodes: WorkflowGraphNode[];
  edges: WorkflowGraphEdge[];
  metadata?: Record<string, unknown>;
};

export type WorkflowVersion = {
  id: string;
  tenant_id: string;
  workflow_definition_id: string;
  version: number;
  graph_json: WorkflowGraph;
  input_schema_json: Record<string, unknown>;
  output_schema_json: Record<string, unknown>;
  checksum: string | null;
  published_at: string | null;
  created_by_user_id: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkflowCompileError = {
  code: string;
  message: string;
  node_id?: string | null;
  node_type?: string | null;
};

export type WorkflowCompileResult = {
  valid: boolean;
  errors: WorkflowCompileError[];
  normalized_graph: WorkflowGraph | null;
  checksum: string | null;
};

export type WorkflowNodeDefinition = {
  type: string;
  version: number;
  category: string;
  display_name: string;
  description: string;
  config_schema: Record<string, unknown>;
  required_capabilities: string[];
  may_pause: boolean;
};

export type WorkflowRun = {
  id: string;
  tenant_id: string;
  automation_id: string | null;
  workflow_definition_id: string;
  workflow_version_id: string;
  brand_id: string | null;
  trigger_type: string;
  trigger_payload: Record<string, unknown>;
  status: string;
  context_snapshot: Record<string, unknown>;
  started_at: string | null;
  finished_at: string | null;
  error_message: string | null;
  correlation_id: string | null;
  created_at: string;
  updated_at: string;
};

export type WorkflowNodeRun = {
  id: string;
  workflow_run_id: string;
  node_id: string;
  node_type: string;
  node_version: number;
  status: string;
  attempt: number;
  input_json: Record<string, unknown>;
  output_json: Record<string, unknown>;
  error_json: Record<string, unknown> | null;
  waiting_reason: string | null;
  resume_token: string | null;
  started_at: string | null;
  finished_at: string | null;
};

export type WorkflowRunDetail = {
  run: WorkflowRun;
  nodes: WorkflowNodeRun[];
};

export type AutomationTarget = {
  id: string;
  social_account_id: string;
  enabled: boolean;
  overrides_json: Record<string, unknown>;
};

export type Automation = {
  id: string;
  tenant_id: string;
  workflow_definition_id: string;
  workflow_version_id: string;
  brand_id: string;
  name: string;
  enabled: boolean;
  trigger_type: string;
  trigger_config: Record<string, unknown>;
  timezone: string;
  next_run_at: string | null;
  last_run_at: string | null;
  settings: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  targets: AutomationTarget[];
};

export type BrandOption = {
  id: string;
  name: string;
  niche?: string | null;
};

export type CompileContextPayload = {
  social_account_ids?: string[];
  require_publish_targets?: boolean;
};

export type NodeTestResult = {
  node_type: string;
  version: number;
  status: string;
  inputs: Record<string, unknown>;
  config: Record<string, unknown>;
  output: Record<string, unknown>;
  error: Record<string, unknown> | null;
  waiting_reason: string | null;
};

export type DryRunOptions = {
  dry_run: boolean;
  mock_generation: boolean;
  simulate_approval: boolean;
};

export const DEFAULT_LINEAR_GRAPH: WorkflowGraph = {
  nodes: [
    { id: "trigger", type: "manual_trigger", version: 1, config: {} },
    { id: "generate", type: "generate_text", version: 1, config: { max_tokens: 400 } },
    { id: "approval", type: "approval", version: 1, config: {} },
    { id: "publish", type: "publish", version: 1, config: { dry_run: true } },
  ],
  edges: [
    { source: "trigger", target: "generate" },
    { source: "generate", target: "approval" },
    { source: "approval", target: "publish", condition: "approved" },
  ],
  metadata: {},
};
