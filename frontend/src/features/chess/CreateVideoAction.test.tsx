import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { CreateVideoAction } from "./CreateVideoAction";

describe("CreateVideoAction", () => {
  it("loads game into video creator and enqueues create", async () => {
    const user = userEvent.setup();
    const onUseInCreator = vi.fn();
    const onCreateVideo = vi.fn();
    render(
      <CreateVideoAction
        onUseInCreator={onUseInCreator}
        onCreateVideo={onCreateVideo}
      />,
    );
    await user.click(screen.getByRole("button", { name: /use in create/i }));
    await user.click(screen.getByRole("button", { name: /create video/i }));
    expect(onUseInCreator).toHaveBeenCalledTimes(1);
    expect(onCreateVideo).toHaveBeenCalledTimes(1);
  });

  it("shows loading label while creating", () => {
    render(<CreateVideoAction onCreateVideo={() => undefined} creating />);
    expect(screen.getByRole("button", { name: /starting/i })).toBeDisabled();
  });
});
