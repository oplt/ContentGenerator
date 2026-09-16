import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as Tooltip from "@radix-ui/react-tooltip";
import type { ChessGame } from "../../api/chessData";
import { GameSearchPanel } from "./GameSearchPanel";
import { useChessGames } from "./hooks/useChessGames";

vi.mock("./hooks/useChessGames", () => ({
  useChessGames: vi.fn(),
}));

const useGames = vi.mocked(useChessGames);

const SAMPLE: ChessGame = {
  id: "g-search",
  tenant_id: "t1",
  white_player: "Kasparov",
  black_player: "Deep Blue",
  year: 1997,
  starting_fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  normalized_pgn: "1. e4 c5",
  move_count: 2,
  is_famous: false,
  historical_tags: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

function renderPanel(ui: React.ReactElement) {
  return render(<Tooltip.Provider delayDuration={0}>{ui}</Tooltip.Provider>);
}

describe("GameSearchPanel", () => {
  beforeEach(() => {
    useGames.mockReset();
  });

  it("shows historical search loading and empty states", () => {
    useGames.mockReturnValue({
      isLoading: true,
      isError: false,
      isSuccess: false,
      data: undefined,
      refetch: vi.fn(),
    } as never);
    const { rerender } = renderPanel(<GameSearchPanel onSelect={vi.fn()} />);
    expect(screen.getByRole("status", { name: /searching catalog/i })).toBeInTheDocument();

    useGames.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: { items: [], has_more: false },
      refetch: vi.fn(),
    } as never);
    rerender(
      <Tooltip.Provider delayDuration={0}>
        <GameSearchPanel onSelect={vi.fn()} />
      </Tooltip.Provider>,
    );
    expect(screen.getByText(/no matching games/i)).toBeInTheDocument();
    expect(screen.getByText(/no games matched these filters/i)).toBeInTheDocument();
  });

  it("renders search hits and handles filter submit", async () => {
    const user = userEvent.setup();
    useGames.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: { items: [SAMPLE], has_more: false },
      refetch: vi.fn(),
    } as never);
    renderPanel(<GameSearchPanel onSelect={vi.fn()} />);
    expect(screen.getByText(/kasparov/i)).toBeInTheDocument();
    await user.type(screen.getByPlaceholderText("Player"), "Kasparov");
    await user.click(screen.getByRole("button", { name: /search games/i }));
    expect(useGames).toHaveBeenCalled();
  });

  it("renders recent search hit distinctly from famous catalog", () => {
    useGames.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: {
        items: [
          {
            ...SAMPLE,
            is_famous: false,
            is_recent: true,
            source_provider: "lichess_masters",
          },
        ],
        has_more: false,
      },
      refetch: vi.fn(),
    } as never);
    renderPanel(<GameSearchPanel onSelect={vi.fn()} />);
    expect(screen.getByText(/kasparov/i)).toBeInTheDocument();
    expect(screen.getByText("Recent")).toBeInTheDocument();
    // Card badge only — filter still says "Famous only".
    expect(screen.queryByText(/^Famous$/)).not.toBeInTheDocument();
  });

  it("surfaces provider errors with retry", async () => {
    const user = userEvent.setup();
    const refetch = vi.fn();
    useGames.mockReturnValue({
      isLoading: false,
      isError: true,
      isSuccess: false,
      error: new Error("rate limited"),
      refetch,
    } as never);
    renderPanel(<GameSearchPanel onSelect={vi.fn()} />);
    expect(screen.getByText(/could not search games/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(refetch).toHaveBeenCalled();
  });
});
