import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import WorkflowsPage from "./WorkflowsPage";
import { useWorkspaceStore } from "../store/workspaceStore";

const listWorkflowDefinitions = vi.fn();
const createWorkflowDefinition = vi.fn();
const saveWorkflowDraft = vi.fn();
const navigate = vi.fn();

vi.mock("../api/workflows", async () => {
  const actual = await vi.importActual<typeof import("../api/workflows")>("../api/workflows");
  return {
    ...actual,
    listWorkflowDefinitions: (...args: unknown[]) => listWorkflowDefinitions(...args),
    createWorkflowDefinition: (...args: unknown[]) => createWorkflowDefinition(...args),
    saveWorkflowDraft: (...args: unknown[]) => saveWorkflowDraft(...args),
  };
});

vi.mock("react-router-dom", async () => {
  const actual = await vi.importActual<typeof import("react-router-dom")>("react-router-dom");
  return {
    ...actual,
    useNavigate: () => navigate,
  };
});

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <WorkflowsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("WorkflowsPage", () => {
  beforeEach(() => {
    listWorkflowDefinitions.mockReset();
    createWorkflowDefinition.mockReset();
    saveWorkflowDraft.mockReset();
    navigate.mockReset();
    useWorkspaceStore.setState({ tenantId: "tenant-1", tenantName: "Tenant" });
    listWorkflowDefinitions.mockResolvedValue([
      {
        id: "wf-1",
        tenant_id: "tenant-1",
        name: "Daily chess",
        slug: "daily-chess",
        description: null,
        status: "active",
        current_version_id: "ver-1",
        created_by_user_id: null,
        created_at: "2026-01-01T00:00:00Z",
        updated_at: "2026-01-01T00:00:00Z",
      },
    ]);
  });

  it("lists workflows and creates a draft graph", async () => {
    const user = userEvent.setup();
    createWorkflowDefinition.mockResolvedValue({
      id: "wf-2",
      tenant_id: "tenant-1",
      name: "New flow",
      slug: "new-flow",
      description: null,
      status: "draft",
      current_version_id: null,
      created_by_user_id: null,
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    saveWorkflowDraft.mockResolvedValue({});

    renderPage();
    expect(await screen.findByText("Daily chess")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Workflow name"), "New flow");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(createWorkflowDefinition).toHaveBeenCalled();
      expect(saveWorkflowDraft).toHaveBeenCalled();
      expect(navigate).toHaveBeenCalledWith("/dashboard/workflows/wf-2");
    });
  });
});
