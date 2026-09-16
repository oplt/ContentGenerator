import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ChessDailyPuzzle } from "../../api/chessData";
import * as chessData from "../../api/chessData";
import { DailyPuzzlePanel } from "./DailyPuzzlePanel";
import { useDailyChessPuzzle } from "./hooks/useChessPuzzles";

vi.mock("../../hooks/useTenantScope", () => ({
  useTenantScope: () => ({ tenantId: "t1", enabled: true }),
}));

vi.mock("./hooks/useChessPuzzles", () => ({
  useDailyChessPuzzle: vi.fn(),
  useChessPuzzles: vi.fn(),
}));

vi.mock("../../api/chessData", async () => {
  const actual = await vi.importActual<typeof chessData>("../../api/chessData");
  return {
    ...actual,
    refreshDailyChessPuzzle: vi.fn(),
  };
});

const useDaily = vi.mocked(useDailyChessPuzzle);

const FRESH: ChessDailyPuzzle = {
  id: "d1",
  tenant_id: "t1",
  external_id: "daily-1",
  provider: "lichess_puzzles",
  starting_fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  solution_moves_uci: ["e2e4"],
  solution_moves_san: ["e4"],
  themes: ["opening"],
  opening_tags: [],
  created_at: "2026-09-16T00:00:00Z",
  updated_at: "2026-09-16T00:00:00Z",
  is_stale: false,
  freshness: "fresh",
  daily_utc: "2026-09-16",
  retrieved_at: "2026-09-16T01:00:00Z",
};

function renderPanel(selectedId: string | null = null) {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <DailyPuzzlePanel selectedId={selectedId} onSelect={vi.fn()} />
    </QueryClientProvider>,
  );
}

describe("DailyPuzzlePanel (§31 local-first / freshness)", () => {
  beforeEach(() => {
    useDaily.mockReset();
    vi.mocked(chessData.refreshDailyChessPuzzle).mockReset();
  });

  it("renders local fresh daily puzzle without calling Lichess", () => {
    useDaily.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: FRESH,
      refetch: vi.fn(),
    } as never);
    renderPanel();
    expect(screen.getByText(/Daily · lichess_puzzles\/daily-1/i)).toBeInTheDocument();
    expect(screen.getByText("Fresh")).toBeInTheDocument();
    expect(screen.queryByText(/provider offline/i)).not.toBeInTheDocument();
    // Hook is the SignalForge GET — never a provider client.
    expect(useDaily).toHaveBeenCalled();
  });

  it("shows stale cue for last persisted daily", () => {
    useDaily.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        ...FRESH,
        is_stale: true,
        freshness: "stale",
        daily_utc: "2020-01-01",
      },
      refetch: vi.fn(),
    } as never);
    renderPanel();
    expect(screen.getByText("Stale")).toBeInTheDocument();
    expect(screen.getByText(/Showing 2020-01-01/i)).toBeInTheDocument();
  });

  it("sync button refreshes via SignalForge API only", async () => {
    const user = userEvent.setup();
    useDaily.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: FRESH,
      refetch: vi.fn(),
    } as never);
    vi.mocked(chessData.refreshDailyChessPuzzle).mockResolvedValue({
      ...FRESH,
      external_id: "daily-2",
    });
    renderPanel();
    await user.click(screen.getByRole("button", { name: /sync from provider/i }));
    expect(chessData.refreshDailyChessPuzzle).toHaveBeenCalledTimes(1);
  });

  it("shows local-catalog miss message on error", () => {
    useDaily.mockReturnValue({
      isLoading: false,
      isError: true,
      isSuccess: false,
      error: new Error("Daily puzzle not in local catalog yet — run daily puzzle sync"),
      refetch: vi.fn(),
    } as never);
    renderPanel();
    expect(screen.getByText(/daily puzzle unavailable/i)).toBeInTheDocument();
    expect(screen.getByText(/local catalog/i)).toBeInTheDocument();
  });
});
