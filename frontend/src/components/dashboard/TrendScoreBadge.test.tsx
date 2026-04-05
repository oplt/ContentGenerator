import { render, screen } from "@testing-library/react";
import { TrendScoreBadge } from "./TrendScoreBadge";

describe("TrendScoreBadge", () => {
  it("renders a formatted score", () => {
    render(<TrendScoreBadge score={0.87} />);
    expect(screen.getByText("0.87")).toBeInTheDocument();
  });
});
