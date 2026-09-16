import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ChessMove } from "../../api/chessData";
import { MoveViewer } from "./MoveViewer";

const MOVES: ChessMove[] = [
  {
    ply: 1,
    move_number: 1,
    side: "white",
    san: "e4",
    uci: "e2e4",
    fen_before: "start",
    fen_after: "after1",
  },
  {
    ply: 2,
    move_number: 1,
    side: "black",
    san: "e5",
    uci: "e7e5",
    fen_before: "after1",
    fen_after: "after2",
  },
];

describe("MoveViewer", () => {
  it("shows empty state", () => {
    render(<MoveViewer moves={[]} />);
    expect(screen.getByText("No moves.")).toBeInTheDocument();
  });

  it("navigates plies via click", async () => {
    const user = userEvent.setup();
    const onSelectPly = vi.fn();
    render(<MoveViewer moves={MOVES} activePly={1} onSelectPly={onSelectPly} />);
    expect(screen.getByText("e4")).toBeInTheDocument();
    expect(screen.getByText("e5")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: /e5/i }));
    expect(onSelectPly).toHaveBeenCalledWith(2);
  });
});
