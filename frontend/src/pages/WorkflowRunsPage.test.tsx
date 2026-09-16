import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import WorkflowRunsPage from "./WorkflowRunsPage";
import { useWorkspaceStore } from "../store/workspaceStore";

const listWorkflowRuns = vi.fn();

vi.mock("../api/workflows", async () => {
  const actual = await vi.importActual<typeof import("../api/workflows")>("../api/workflows");
  return {
    ...actual,
    listWorkflowRuns: (...args: unknown[]) => listWorkflowRuns(...args),
  };
});

vi.mock("../hooks/useDocumentVisible", () => ({
  useDocumentVisible: () => true,
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <WorkflowRunsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("WorkflowRunsPage", () => {
  beforeEach(() => {
    listWorkflowRuns.mockReset();
    useWorkspaceStore.setState({ tenantId: "tenant-1", tenantName: "Tenant" });
    listWorkflowRuns.mockResolvedValue([
      {
        id: "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
        tenant_id: "tenant-1",
        status: "waiting",
        trigger_type: "dry_run",
        started_at: "2026-01-01T12:00:00Z",
        error_message: null,
      },
    ]);
  });

  it("shows run status badges and open link", async () => {
    renderPage();
    expect(await screen.findByText("waiting")).toBeInTheDocument();
    expect(screen.getByText("dry_run", { exact: false })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Open" })).toHaveAttribute(
      "href",
      "/dashboard/runs/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    );
  });
});
