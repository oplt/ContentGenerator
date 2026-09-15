import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import type { SocialAccount } from "../../api/publishing";
import { SocialAccountSelector } from "./SocialAccountSelector";

function account(overrides: Partial<SocialAccount> = {}): SocialAccount {
  return {
    id: overrides.id ?? "acc-1",
    platform: overrides.platform ?? "x",
    display_name: overrides.display_name ?? "Main",
    handle: overrides.handle ?? "@main",
    account_external_id: "ext-1",
    status: overrides.status ?? "connected",
    capability_flags: overrides.capability_flags ?? { draft: "true" },
    metadata: overrides.metadata ?? { mode: "stub" },
  };
}

describe("SocialAccountSelector", () => {
  it("selects two same-platform accounts independently", async () => {
    const user = userEvent.setup();
    const onChange = vi.fn();
    const accounts = [
      account({ id: "a", display_name: "A", handle: "@a" }),
      account({ id: "b", display_name: "B", handle: "@b" }),
    ];

    const { rerender } = render(
      <SocialAccountSelector accounts={accounts} selectedIds={[]} onChange={onChange} />
    );

    await user.click(screen.getByLabelText(/x · @a/i));
    expect(onChange).toHaveBeenLastCalledWith(["a"]);

    rerender(<SocialAccountSelector accounts={accounts} selectedIds={["a"]} onChange={onChange} />);
    await user.click(screen.getByLabelText(/x · @b/i));
    expect(onChange).toHaveBeenLastCalledWith(["a", "b"]);
  });

  it("disables quarantined accounts", () => {
    render(
      <SocialAccountSelector
        accounts={[account({ id: "q", status: "quarantined", handle: "@q" })]}
        selectedIds={[]}
        onChange={vi.fn()}
      />
    );
    expect(screen.getByRole("checkbox")).toBeDisabled();
  });
});
