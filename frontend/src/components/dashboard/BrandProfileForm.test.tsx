import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import * as Tooltip from "@radix-ui/react-tooltip";
import { BrandProfileForm } from "./BrandProfileForm";

describe("BrandProfileForm", () => {
  it("submits edited values", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
      <Tooltip.Provider delayDuration={0}>
        <BrandProfileForm
          defaultValues={{
            name: "Default Brand",
            niche: "general",
            tone: "authoritative",
            audience: "Audience",
            default_cta: "Follow",
            voice_notes: "",
          }}
          onSubmit={onSubmit}
        />
      </Tooltip.Provider>
    );

    await user.clear(screen.getByPlaceholderText("Brand name"));
    await user.type(screen.getByPlaceholderText("Brand name"), "SignalForge Media");
    await user.click(screen.getByRole("button", { name: "Save Brand Profile" }));

    expect(onSubmit).toHaveBeenCalled();
  });
});
