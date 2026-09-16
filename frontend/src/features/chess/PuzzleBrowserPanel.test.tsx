import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ChessPuzzle } from "../../api/chessData";
import { PuzzleBrowserPanel } from "./PuzzleBrowserPanel";
import { useChessPuzzles } from "./hooks/useChessPuzzles";

vi.mock("./hooks/useChessPuzzles", () => ({
  useChessPuzzles: vi.fn(),
}));

const usePuzzles = vi.mocked(useChessPuzzles);

const SAMPLE: ChessPuzzle = {
  id: "p1",
  tenant_id: "t1",
  external_id: "abc",
  provider: "lichess_puzzles",
  starting_fen: "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
  solution_moves_uci: ["e7e5"],
  solution_moves_san: ["e5"],
  rating: 1500,
  themes: ["mate"],
  opening_tags: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("PuzzleBrowserPanel", () => {
  beforeEach(() => {
    usePuzzles.mockReset();
  });

  it("shows loading, empty, and list states for puzzle viewer", () => {
    usePuzzles.mockReturnValue({
      isLoading: true,
      isError: false,
      isSuccess: false,
      refetch: vi.fn(),
    } as never);
    const { rerender } = render(<PuzzleBrowserPanel onSelect={vi.fn()} />);
    expect(screen.getByRole("status", { name: /searching puzzles/i })).toBeInTheDocument();

    usePuzzles.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: { items: [], has_more: false },
      refetch: vi.fn(),
    } as never);
    rerender(<PuzzleBrowserPanel onSelect={vi.fn()} />);
    expect(screen.getByText(/no matching puzzles/i)).toBeInTheDocument();
    expect(screen.getByText(/no puzzles matched these filters/i)).toBeInTheDocument();

    usePuzzles.mockReturnValue({
      isLoading: false,
      isError: false,
      isSuccess: true,
      data: { items: [SAMPLE], has_more: false },
      refetch: vi.fn(),
    } as never);
    rerender(<PuzzleBrowserPanel onSelect={vi.fn()} />);
    expect(screen.getByText(/abc/i)).toBeInTheDocument();
  });

  it("retries after puzzle search failure", async () => {
    const user = userEvent.setup();
    const refetch = vi.fn();
    usePuzzles.mockReturnValue({
      isLoading: false,
      isError: true,
      isSuccess: false,
      error: new Error("provider down"),
      refetch,
    } as never);
    render(<PuzzleBrowserPanel onSelect={vi.fn()} />);
    expect(screen.getByText(/could not search puzzles/i)).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /retry/i }));
    expect(refetch).toHaveBeenCalled();
  });
});
