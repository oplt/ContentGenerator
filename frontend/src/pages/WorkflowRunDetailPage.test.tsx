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
    resumeWorkflowRun: vi.fn(),
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
    </QueryClientProvider>
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
        status: "waiting",
        trigger_type: "manual",
        correlation_id: "corr-1",
        error_message: null,
      },
      nodes: [
        {
          id: "nr-1",
          node_id: "generate",
          node_type: "generate_text",
          status: "succeeded",
          attempt: 1,
          input_json: { prompt: "hi" },
          output_json: { text: "hello" },
          error_json: null,
          resume_token: null,
        },
        {
          id: "nr-2",
          node_id: "approval",
          node_type: "approval",
          status: "waiting",
          attempt: 1,
          input_json: {},
          output_json: {},
          error_json: null,
          resume_token: "tok-1",
        },
      ],
    });
  });

  it("renders node timeline and resume action when waiting", async () => {
    renderPage();
    expect(await screen.findByText(/generate · generate_text/)).toBeInTheDocument();
    expect(screen.getByText(/approval · approval/)).toBeInTheDocument();
    expect(screen.getAllByText("waiting").length).toBeGreaterThan(0);
    expect(screen.getByRole("button", { name: "Resume (approval)" })).toBeInTheDocument();
  });
});
