import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ChessGame, ChessMove } from "../../api/chessData";
import { GameDetails } from "./GameDetails";
import { useChessGameMoves } from "./hooks/useChessGames";

vi.mock("./hooks/useChessGames", () => ({
  useChessGameMoves: vi.fn(),
}));

vi.mock("./ContentOpportunityPanel", () => ({
  ContentOpportunityPanel: () => null,
}));
vi.mock("./ProvenancePanel", () => ({
  ProvenancePanel: () => null,
}));
vi.mock("./AnalyzeGameAction", () => ({
  AnalyzeGameAction: () => null,
}));

const useMoves = vi.mocked(useChessGameMoves);

const GAME: ChessGame = {
  id: "detail-1",
  tenant_id: "t1",
  white_player: "White",
  black_player: "Black",
  famous_title: "Sample Duel",
  event: "Match",
  year: 2020,
  result: "1-0",
  source_provider: "pgn_archive",
  starting_fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  normalized_pgn: "1. e4 e5",
  move_count: 2,
  is_famous: true,
  historical_tags: ["famous"],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const MOVES: ChessMove[] = [
  {
    ply: 1,
    move_number: 1,
    side: "white",
    san: "e4",
    uci: "e2e4",
    fen_before: GAME.starting_fen,
    fen_after: "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
  },
];

describe("GameDetails", () => {
  beforeEach(() => {
    useMoves.mockReset();
  });

  it("shows game detail, move navigation, and load into video editor", async () => {
    const user = userEvent.setup();
    const onUseInCreator = vi.fn();
    useMoves.mockReturnValue({
      isLoading: false,
      data: MOVES,
    } as never);

    render(<GameDetails game={GAME} onUseInCreator={onUseInCreator} />);
    expect(screen.getByText("Sample Duel")).toBeInTheDocument();
    expect(screen.getByText("Game date")).toBeInTheDocument();
    expect(screen.getByText(/Famous catalog entry/i)).toBeInTheDocument();
    expect(screen.getByText("e4")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /e4/i }));
    await user.click(screen.getByRole("button", { name: /use in create/i }));
    expect(onUseInCreator).toHaveBeenCalledWith(GAME);
  });

  it("shows move loading state", () => {
    useMoves.mockReturnValue({ isLoading: true, data: undefined } as never);
    render(<GameDetails game={GAME} />);
    expect(screen.getByText(/loading moves/i)).toBeInTheDocument();
  });
});
