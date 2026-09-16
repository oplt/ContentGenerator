import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ChessGame } from "../../api/chessData";
import { GameCard } from "./GameCard";

const SAMPLE: ChessGame = {
  id: "g-card",
  tenant_id: "t1",
  white_player: "Fischer",
  black_player: "Spassky",
  site: "Reykjavik",
  year: 1972,
  round: "6",
  opening: "Queen's Gambit Declined",
  starting_fen: "rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1",
  normalized_pgn: "1. d4 d5",
  move_count: 2,
  is_famous: true,
  historical_tags: ["famous"],
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("GameCard", () => {
  it("renders research-style meta, famous badge, and content actions", async () => {
    const user = userEvent.setup();
    const onSelect = vi.fn();
    const onView = vi.fn();
    const onAnalyze = vi.fn();
    const onCreateVideo = vi.fn();

    render(
      <GameCard
        game={SAMPLE}
        onSelect={onSelect}
        onView={onView}
        onAnalyze={onAnalyze}
        onCreateVideo={onCreateVideo}
      />,
    );

    expect(screen.getByText("Fischer vs Spassky")).toBeInTheDocument();
    expect(screen.getByText(/Reykjavik · 1972 · Game 6/)).toBeInTheDocument();
    expect(screen.getByText("Queen's Gambit Declined")).toBeInTheDocument();
    expect(screen.getByText(/★ Famous/)).toBeInTheDocument();

    await user.click(screen.getByRole("button", { name: /view game/i }));
    await user.click(screen.getByRole("button", { name: /^analyze$/i }));
    await user.click(screen.getByRole("button", { name: /create video/i }));

    expect(onView).toHaveBeenCalledWith(SAMPLE);
    expect(onAnalyze).toHaveBeenCalledWith(SAMPLE);
    expect(onCreateVideo).toHaveBeenCalledWith(SAMPLE);
  });
});
