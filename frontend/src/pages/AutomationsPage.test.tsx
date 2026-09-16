import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import AutomationsPage from "./AutomationsPage";
import { useWorkspaceStore } from "../store/workspaceStore";

const listAutomations = vi.fn();
const listWorkflowDefinitions = vi.fn();
const listWorkflowBrands = vi.fn();
const createAutomation = vi.fn();
const updateAutomation = vi.fn();
const getSocialAccounts = vi.fn();

vi.mock("../api/workflows", async () => {
  const actual = await vi.importActual<typeof import("../api/workflows")>("../api/workflows");
  return {
    ...actual,
    listAutomations: (...args: unknown[]) => listAutomations(...args),
    listWorkflowDefinitions: (...args: unknown[]) => listWorkflowDefinitions(...args),
    listWorkflowBrands: (...args: unknown[]) => listWorkflowBrands(...args),
    createAutomation: (...args: unknown[]) => createAutomation(...args),
    updateAutomation: (...args: unknown[]) => updateAutomation(...args),
  };
});

vi.mock("../api/publishing", () => ({
  getSocialAccounts: (...args: unknown[]) => getSocialAccounts(...args),
}));

vi.mock("../hooks/useAccountSelection", () => ({
  useAccountSelection: () => ({
    selectedIds: ["acct-1"],
    setSelectedIds: vi.fn(),
  }),
}));

vi.mock("../components/dashboard/SocialAccountSelector", () => ({
  SocialAccountSelector: () => <div>Targets</div>,
}));

function renderPage() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <MemoryRouter>
        <AutomationsPage />
      </MemoryRouter>
    </QueryClientProvider>
  );
}

describe("AutomationsPage", () => {
  beforeEach(() => {
    listAutomations.mockReset();
    listWorkflowDefinitions.mockReset();
    listWorkflowBrands.mockReset();
    createAutomation.mockReset();
    updateAutomation.mockReset();
    getSocialAccounts.mockReset();
    useWorkspaceStore.setState({ tenantId: "tenant-1", tenantName: "Tenant" });
    listAutomations.mockResolvedValue([
      {
        id: "auto-1",
        name: "Chess morning",
        enabled: false,
        trigger_type: "manual",
        next_run_at: null,
        targets: [{ social_account_id: "acct-1" }],
      },
    ]);
    listWorkflowDefinitions.mockResolvedValue([
      {
        id: "wf-1",
        name: "Historical chess",
        current_version_id: "ver-1",
      },
    ]);
    listWorkflowBrands.mockResolvedValue([{ id: "brand-1", name: "Chess" }]);
    getSocialAccounts.mockResolvedValue([]);
  });

  it("renders automation form and creates from published workflow", async () => {
    const user = userEvent.setup();
    createAutomation.mockResolvedValue({ id: "auto-2" });

    renderPage();
    expect(await screen.findByText("Chess morning")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Automation name"), "Evening run");
    await user.selectOptions(screen.getByDisplayValue("Select published workflow"), "wf-1");
    await user.click(screen.getByRole("button", { name: "Create" }));

    await waitFor(() => {
      expect(createAutomation).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Evening run",
          workflow_definition_id: "wf-1",
          social_account_ids: ["acct-1"],
        })
      );
    });
  });
});
