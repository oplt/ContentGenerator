import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { CatalogAdminSyncPanel } from "./CatalogAdminSyncPanel";
import * as chessData from "../../api/chessData";

vi.mock("../auth/AuthContext", () => ({
  useAuth: () => ({
    currentUser: {
      id: "u1",
      memberships: [
        {
          tenant_id: "t1",
          role: { permission_codes: ["content:write"] },
        },
      ],
    },
  }),
}));

vi.mock("../../hooks/useTenantScope", () => ({
  useTenantScope: () => ({ tenantId: "t1", enabled: true }),
}));

vi.mock("../../api/chessData", async () => {
  const actual = await vi.importActual<typeof chessData>("../../api/chessData");
  return {
    ...actual,
    enqueueChessCatalogJob: vi.fn(),
    getChessCatalogJob: vi.fn(),
  };
});

function renderPanel() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <CatalogAdminSyncPanel />
    </QueryClientProvider>,
  );
}

describe("CatalogAdminSyncPanel (§25)", () => {
  beforeEach(() => {
    vi.mocked(chessData.enqueueChessCatalogJob).mockReset();
    vi.mocked(chessData.getChessCatalogJob).mockReset();
    vi.mocked(chessData.enqueueChessCatalogJob).mockResolvedValue({
      id: "job-1",
      tenant_id: "t1",
      kind: "provider_sync",
      status: "queued",
      progress: 0,
      params: {},
      result: {},
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
    vi.mocked(chessData.getChessCatalogJob).mockResolvedValue({
      id: "job-1",
      tenant_id: "t1",
      kind: "provider_sync",
      status: "queued",
      progress: 0,
      params: {},
      result: {},
      created_at: "2026-01-01T00:00:00Z",
      updated_at: "2026-01-01T00:00:00Z",
    });
  });

  it("enqueues provider_sync without browsing coupling", async () => {
    const user = userEvent.setup();
    renderPanel();
    expect(screen.getByTestId("catalog-admin-sync")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /run recent-game sync/i }));
    expect(chessData.enqueueChessCatalogJob).toHaveBeenCalledWith({
      kind: "provider_sync",
      params: { provider: "lichess_masters", max_games: 15 },
    });
  });

  it("enqueues enrich_famous and daily_puzzle_sync", async () => {
    const user = userEvent.setup();
    renderPanel();
    await user.click(screen.getByRole("button", { name: /enrich famous catalog/i }));
    expect(chessData.enqueueChessCatalogJob).toHaveBeenCalledWith({
      kind: "enrich_famous",
      params: {},
    });
    await user.click(screen.getByRole("button", { name: /refresh daily puzzle/i }));
    expect(chessData.enqueueChessCatalogJob).toHaveBeenCalledWith({
      kind: "daily_puzzle_sync",
      params: {},
    });
  });
});
