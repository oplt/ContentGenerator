import { render, screen } from "@testing-library/react";
import type { ChessPuzzle } from "../../api/chessData";
import { PuzzleViewer } from "./PuzzleViewer";

const SAMPLE: ChessPuzzle = {
  id: "p1",
  tenant_id: "t1",
  external_id: "xyz",
  provider: "lichess_puzzles",
  starting_fen: "rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1",
  solution_moves_uci: ["e7e5"],
  solution_moves_san: ["e5"],
  rating: 1600,
  themes: ["mate"],
  opening_tags: [],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("PuzzleViewer", () => {
  it("shows empty state", () => {
    render(<PuzzleViewer puzzle={null} />);
    expect(screen.getByText(/browse the puzzle catalog/i)).toBeInTheDocument();
  });

  it("renders puzzle detail and solution", () => {
    render(<PuzzleViewer puzzle={SAMPLE} />);
    expect(screen.getByText(/lichess_puzzles\/xyz/i)).toBeInTheDocument();
    expect(screen.getByText(/solution:\s*e5/i)).toBeInTheDocument();
    expect(screen.getByText(/rating 1600/i)).toBeInTheDocument();
  });
});
