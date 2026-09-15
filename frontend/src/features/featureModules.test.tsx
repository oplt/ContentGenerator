import { render, screen } from "@testing-library/react";
import { FormField, PasswordField, StatusMessage } from "../features/auth/fields";
import { GENERIC_SIGN_IN_ERROR } from "../features/auth/messages";
import { PERIOD_LABELS, PERIODS } from "../features/trending";
import { SETTINGS_TABS, SOCIAL_PLATFORM_DEFINITIONS } from "../features/settings";
import { SOURCES_TABS, SOURCE_CATEGORIES } from "../features/sources";

describe("T7.2 feature module characterization", () => {
  it("exposes auth field primitives and stable error copy", () => {
    render(<FormField label="Email" />);
    expect(screen.getByText("Email")).toBeInTheDocument();
    render(<PasswordField label="Password" />);
    expect(screen.getByLabelText("Show password")).toBeInTheDocument();
    render(<StatusMessage variant="error" message={GENERIC_SIGN_IN_ERROR} />);
    expect(screen.getByText(GENERIC_SIGN_IN_ERROR)).toBeInTheDocument();
  });

  it("keeps settings/sources/trending constants stable for deep links", () => {
    expect(SETTINGS_TABS).toEqual(["general", "workflow", "whatsapp", "telegram", "social"]);
    expect(SOCIAL_PLATFORM_DEFINITIONS.map((item) => item.platform)).toEqual([
      "youtube",
      "instagram",
      "tiktok",
      "x",
      "bluesky",
    ]);
    expect(SOURCES_TABS).toEqual(["configured", "add"]);
    expect(SOURCE_CATEGORIES).toContain("technology");
    expect(PERIODS).toEqual(["daily", "weekly", "monthly"]);
    expect(PERIOD_LABELS.daily).toBe("Today");
  });
});
