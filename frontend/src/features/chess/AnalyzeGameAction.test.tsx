import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ChessAnalysisJob } from "../../api/chessData";
import * as chessData from "../../api/chessData";
import { AnalyzeGameAction } from "./AnalyzeGameAction";

vi.mock("../../hooks/useTenantScope", () => ({
  useTenantScope: () => ({ tenantId: "t1", enabled: true }),
}));

vi.mock("../../api/chessData", async () => {
  const actual = await vi.importActual<typeof chessData>("../../api/chessData");
  return {
    ...actual,
    enqueueChessGameAnalysis: vi.fn(),
    getChessAnalysisJob: vi.fn(),
    getChessGameAnalysis: vi.fn(),
  };
});

const COMPLETED: ChessAnalysisJob = {
  id: "job-1",
  tenant_id: "t1",
  chess_game_id: "g1",
  status: "completed",
  progress: 1,
  engine_name: "Stockfish",
  engine_version: "16",
  depth: 12,
  hash_mb: 16,
  threads: 1,
  analysis_settings: {},
  ply_count: 0,
  positions: [],
  critical_moments: [],
  tactical_patterns: [],
  created_at: "2026-09-16T00:00:00Z",
  updated_at: "2026-09-16T00:00:00Z",
  reused: true,
};

function renderAction() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <AnalyzeGameAction gameId="g1" />
    </QueryClientProvider>,
  );
}

describe("AnalyzeGameAction (§31 analysis reuse)", () => {
  beforeEach(() => {
    vi.mocked(chessData.getChessGameAnalysis).mockReset();
    vi.mocked(chessData.getChessAnalysisJob).mockReset();
    vi.mocked(chessData.enqueueChessGameAnalysis).mockReset();
  });

  it("shows reused cached analysis from SignalForge GET", async () => {
    vi.mocked(chessData.getChessGameAnalysis).mockResolvedValue(COMPLETED);
    vi.mocked(chessData.getChessAnalysisJob).mockResolvedValue(COMPLETED);
    renderAction();
    await waitFor(() => {
      expect(screen.getByText(/Cached analysis reused/i)).toBeInTheDocument();
    });
    expect(screen.getByText(/Status: completed · Stockfish 16/i)).toBeInTheDocument();
    expect(chessData.getChessGameAnalysis).toHaveBeenCalledWith("g1");
  });

  it("enqueues analysis via SignalForge API", async () => {
    const user = userEvent.setup();
    vi.mocked(chessData.getChessGameAnalysis).mockRejectedValue(new Error("not found"));
    const queued = {
      ...COMPLETED,
      reused: false,
      status: "queued" as const,
      progress: 0,
    };
    vi.mocked(chessData.enqueueChessGameAnalysis).mockResolvedValue(queued);
    vi.mocked(chessData.getChessAnalysisJob).mockResolvedValue(queued);
    renderAction();
    await waitFor(() => {
      expect(screen.getByRole("button", { name: /analyze with stockfish/i })).toBeEnabled();
    });
    await user.click(screen.getByRole("button", { name: /analyze with stockfish/i }));
    expect(chessData.enqueueChessGameAnalysis).toHaveBeenCalledWith("g1", {});
  });
});
