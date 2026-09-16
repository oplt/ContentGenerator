import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as Tooltip from "@radix-ui/react-tooltip";
import { useState } from "react";
import type { ChessGameSearchParams } from "../../api/chessData";
import { GameFilters } from "./GameFilters";

function FiltersHarness({
  onSubmit,
}: {
  onSubmit: (value: ChessGameSearchParams) => void;
}) {
  const [value, setValue] = useState<ChessGameSearchParams>({ limit: 20 });
  return (
    <Tooltip.Provider delayDuration={0}>
      <GameFilters
        value={value}
        onChange={setValue}
        onSubmit={() => onSubmit(value)}
      />
    </Tooltip.Provider>
  );
}

describe("GameFilters", () => {
  it("updates filter state and submits search", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn();
    render(<FiltersHarness onSubmit={onSubmit} />);

    await user.type(screen.getByPlaceholderText("Player"), "Carlsen");
    await user.type(screen.getByPlaceholderText("ECO"), "C20");
    await user.click(screen.getByLabelText(/famous only/i));
    await user.click(screen.getByRole("button", { name: /search games/i }));

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        player: "Carlsen",
        eco: "C20",
        famous_only: true,
        limit: 20,
      }),
    );
  });
});
