import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ChessGame } from "../../api/chessData";
import { FamousGamesPanel } from "./FamousGamesPanel";
import { useFamousChessGames } from "./hooks/useChessGames";

vi.mock("./hooks/useChessGames", () => ({
  useFamousChessGames: vi.fn(),
}));

const useFamous = vi.mocked(useFamousChessGames);

const SAMPLE: ChessGame = {
  id: "g1",
  tenant_id: "t1",
  white_player: "Morphy",
  black_player: "Duke",
  starting_fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  normalized_pgn: "1. e4 e5",
  move_count: 2,
  is_famous: true,
  famous_title: "The Opera Game",
  historical_tags: ["famous"],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("FamousGamesPanel", () => {
  beforeEach(() => {
    useFamous.mockReset();
  });

  it("shows loading state", () => {
    useFamous.mockReturnValue({ isLoading: true, isError: false, isSuccess: false } as never);
    render(<FamousGamesPanel onSelect={vi.fn()} />);
    expect(screen.getByRole("status", { name: /loading famous games/i })).toBeInTheDocument();
  });

  it("shows empty state", () => {
    useFamous.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: { items: [], has_more: false },
    } as never);
    render(<FamousGamesPanel onSelect={vi.fn()} />);
    expect(screen.getByText(/no famous games yet/i)).toBeInTheDocument();
  });

  it("lists famous games and supports selection", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    useFamous.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: { items: [SAMPLE], has_more: false },
      refetch: vi.fn(),
    } as never);
    render(<FamousGamesPanel onSelect={onSelect} />);
    expect(screen.getByText("The Opera Game")).toBeInTheDocument();
    await user.click(screen.getByText("The Opera Game"));
    expect(onSelect).toHaveBeenCalledWith(SAMPLE);
  });

  it("shows provider error with retry", async () => {
    const user = userEvent.setup();
    const refetch = vi.fn();
    useFamous.mockReturnValue({
      isLoading: false,
      isError: true,
      isSuccess: false,
      error: new Error("upstream timeout"),
      refetch,
    } as never);
    render(<FamousGamesPanel onSelect={vi.fn()} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/could not load famous games/i);
    expect(screen.getByText(/upstream timeout/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(refetch).toHaveBeenCalled();
  });
});
