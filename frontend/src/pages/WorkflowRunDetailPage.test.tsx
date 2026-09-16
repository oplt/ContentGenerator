import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import WorkflowRunDetailPage from "./WorkflowRunDetailPage";
import { useWorkspaceStore } from "../store/workspaceStore";

const getWorkflowRun = vi.fn();

vi.mock("../api/workflows", async () => {
  const actual = await vi.importActual<typeof import("../api/workflows")>("../api/workflows");
  return {
    ...actual,
    getWorkflowRun: (...args: unknown[]) => getWorkflowRun(...args),
    advanceWorkflowRun: vi.fn(),
    cancelWorkflowRun: vi.fn(),
    retryWorkflowNode: vi.fn(),
    retryWorkflowFromNode: vi.fn(),
    resumeWorkflowNode: vi.fn(),
  };
});

vi.mock("../hooks/useDocumentVisible", () => ({
  useDocumentVisible: () => true,
}));

function renderPage(runId = "run-1") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter initialEntries={[`/dashboard/runs/${runId}`]}>
        <Routes>
          <Route path="/dashboard/runs/:runId" element={<WorkflowRunDetailPage />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("WorkflowRunDetailPage", () => {
  beforeEach(() => {
    getWorkflowRun.mockReset();
    useWorkspaceStore.setState({ tenantId: "tenant-1", tenantName: "Tenant" });
    getWorkflowRun.mockResolvedValue({
      run: {
        id: "run-1-abcdefgh",
        tenant_id: "tenant-1",
        automation_id: null,
        workflow_definition_id: "def-1",
        workflow_version_id: "ver-1",
        brand_id: null,
        status: "waiting",
        trigger_type: "manual",
        trigger_payload: {},
        context_snapshot: {},
        correlation_id: "corr-1",
        error_message: null,
        started_at: "2026-01-01T00:00:00Z",
        finished_at: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
      meta: {
        version_number: 3,
        automation_name: null,
        brand_name: "Acme",
      },
      nodes: [
        {
          id: "nr-1",
          workflow_run_id: "run-1-abcdefgh",
          node_id: "generate",
          node_type: "generate_text",
          node_version: 1,
          status: "succeeded",
          attempt: 1,
          duration_ms: 1200,
          input_json: { prompt: "hi" },
          output_json: { text: "hello" },
          error_json: null,
          resume_token: null,
          waiting_reason: null,
          started_at: "2026-01-01T00:00:00Z",
          finished_at: "2026-01-01T00:00:01Z",
          can_resume: false,
          can_retry: false,
        },
        {
          id: "nr-2",
          workflow_run_id: "run-1-abcdefgh",
          node_id: "approval",
          node_type: "approval",
          node_version: 1,
          status: "waiting",
          attempt: 1,
          input_json: {},
          output_json: { approval_request_id: "appr-1" },
          error_json: null,
          resume_token: null,
          waiting_reason: "approval_pending",
          started_at: "2026-01-01T00:00:01Z",
          finished_at: null,
          can_resume: true,
          can_retry: false,
        },
      ],
    });
  });

  it("renders inspection meta and resume without exposing tokens", async () => {
    renderPage();
    expect(await screen.findByText(/generate · generate_text/)).toBeInTheDocument();
    expect(screen.getByText(/v3/)).toBeInTheDocument();
    expect(screen.getByText("Acme")).toBeInTheDocument();
    expect(screen.getByText("corr-1")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Resume" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cancel workflow" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Inspect approval/i })).toBeInTheDocument();
    expect(screen.queryByText("tok-1")).not.toBeInTheDocument();
  });
});
