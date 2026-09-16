import { render, screen } from "@testing-library/react";
import { ChessBoardPreview } from "./ChessBoardPreview";
import {
  CHESS_GAMES_TABS,
  CHESS_PUZZLES_TABS,
  CHESS_WORKSPACE_TABS,
} from "./constants";

describe("chess feature package", () => {
  it("exports workspace tab structure", () => {
    expect(CHESS_WORKSPACE_TABS).toEqual([
      "games",
      "puzzles",
      "create",
      "preview",
      "history",
    ]);
    expect(CHESS_GAMES_TABS).toContain("imported");
    expect(CHESS_PUZZLES_TABS).toEqual(["browse", "daily"]);
  });

  it("renders a FEN board preview", () => {
    render(
      <ChessBoardPreview fen="rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1" />,
    );
    expect(screen.getByRole("img", { name: /chess position preview/i })).toBeInTheDocument();
  });
});
