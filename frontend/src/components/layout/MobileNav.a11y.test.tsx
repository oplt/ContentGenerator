import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { AppShell } from "./AppShell";
import { DataTable } from "../dashboard/DataTable";
import { renderWithProviders } from "../../test/renderWithProviders";
import { useWorkspaceStore } from "../../store/workspaceStore";

const memberships = [
  {
    tenant_id: "t1",
    tenant_name: "Tenant One",
    tenant_slug: "t1",
    status: "active",
    role: {
      id: "r1",
      name: "Owner",
      slug: "owner",
      permission_codes: ["settings:write", "audit:read"],
    },
  },
];

vi.mock("../../features/auth/AuthContext", () => ({
  useAuth: () => ({
    currentUser: {
      id: "u1",
      email: "demo@example.com",
      full_name: "Demo",
      is_verified: true,
      is_admin: true,
      mfa_enabled: true,
      default_tenant_id: "t1",
      rbac_mode: "role_based_placeholder",
      memberships,
    },
    signOut: vi.fn(),
    setActiveTenant: vi.fn(),
  }),
}));

describe("mobile navigation and accessible controls", () => {
  beforeEach(() => {
    useWorkspaceStore.setState({
      tenantId: "t1",
      tenantName: "Tenant One",
      commandPaletteOpen: false,
    });
  });

  it("exposes named topbar controls and a complete mobile drawer", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <AppShell>
        <div>Page</div>
      </AppShell>,
      { initialEntries: ["/dashboard"] }
    );

    expect(screen.getByLabelText("Active workspace")).toBeInTheDocument();
    expect(screen.getByLabelText(/theme/i)).toBeInTheDocument();
    expect(screen.getByLabelText("Open command palette")).toBeInTheDocument();

    await user.click(screen.getByLabelText("Open navigation menu"));
    const drawer = await screen.findByRole("dialog");
    expect(within(drawer).getByRole("link", { name: "Briefs" })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Trending Repos" })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Account" })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Brand" })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Settings" })).toBeInTheDocument();
    expect(within(drawer).getByRole("link", { name: "Audit" })).toBeInTheDocument();
    expect(within(drawer).getByLabelText("Close navigation menu")).toBeInTheDocument();
  });

  it("lists all authorized destinations in the command palette", async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <AppShell>
        <div>Page</div>
      </AppShell>
    );

    await user.click(screen.getByLabelText("Open command palette"));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByLabelText("Search destinations")).toBeInTheDocument();
    expect(within(dialog).getByRole("option", { name: "Briefs" })).toBeInTheDocument();
    expect(within(dialog).getByRole("option", { name: "Account" })).toBeInTheDocument();
    expect(within(dialog).getByRole("option", { name: "Trending Repos" })).toBeInTheDocument();
    expect(within(dialog).getByRole("option", { name: "Settings" })).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Close dialog")).toBeInTheDocument();
  });
});

describe("DataTable", () => {
  it("provides a labeled scroll region and mobile row layout", () => {
    render(
      <MemoryRouter>
        <DataTable
          caption="Audit log entries"
          columns={[
            { key: "action", header: "Action", render: (row: { action: string }) => row.action },
            { key: "message", header: "Message", render: (row: { message: string }) => row.message },
          ]}
          rows={[{ action: "publish", message: "ok" }]}
        />
      </MemoryRouter>
    );

    expect(screen.getByRole("region", { name: "Audit log entries" })).toBeInTheDocument();
    expect(screen.getAllByText("publish").length).toBeGreaterThan(0);
    expect(screen.getAllByText("Action").length).toBeGreaterThan(0);
  });
});
