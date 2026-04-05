import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { BrandProfileForm } from "./BrandProfileForm";

describe("BrandProfileForm", () => {
  it("submits edited values", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockResolvedValue(undefined);
    render(
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
    );

    await user.clear(screen.getByPlaceholderText("Brand name"));
    await user.type(screen.getByPlaceholderText("Brand name"), "SignalForge Media");
    await user.click(screen.getByRole("button", { name: "Save Brand Profile" }));

    expect(onSubmit).toHaveBeenCalled();
  });
});
