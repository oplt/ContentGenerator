import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import MfaSetupPage from "./MfaSetupPage";
import { renderWithProviders } from "../test/renderWithProviders";

const enableMfa = vi.fn().mockResolvedValue({
  secret: "SECRETBASE32",
  provisioning_uri: "otpauth://totp/SignalForge:admin@example.com?secret=SECRETBASE32",
});
const verifyMfa = vi.fn().mockResolvedValue(undefined);
const reloadSession = vi.fn().mockResolvedValue(undefined);
const signOut = vi.fn().mockResolvedValue(undefined);

vi.mock("../api/auth", () => ({
  enableMfa: (...args: unknown[]) => enableMfa(...args),
  verifyMfa: (...args: unknown[]) => verifyMfa(...args),
}));

vi.mock("../features/auth/AuthContext", () => ({
  useAuth: () => ({
    isReady: true,
    isAuthenticated: true,
    currentUser: {
      id: "1",
      email: "admin@example.com",
      full_name: "Admin",
      is_verified: true,
      is_admin: true,
      mfa_enabled: false,
      default_tenant_id: "t1",
      rbac_mode: "role_based_placeholder",
      memberships: [],
    },
    reloadSession,
    signOut,
  }),
}));

describe("MfaSetupPage", () => {
  beforeEach(() => {
    enableMfa.mockClear();
    verifyMfa.mockClear();
    reloadSession.mockClear();
  });

  it("enrolls and verifies MFA without a dead-end", async () => {
    const user = userEvent.setup();
    renderWithProviders(<MfaSetupPage />);

    await user.click(screen.getByRole("button", { name: "Start MFA enrollment" }));
    expect(await screen.findByText("SECRETBASE32")).toBeInTheDocument();

    await user.type(screen.getByLabelText("Verification code"), "123456");
    await user.click(screen.getByRole("button", { name: "Confirm and enable MFA" }));

    expect(verifyMfa).toHaveBeenCalledWith({ code: "123456" });
    expect(reloadSession).toHaveBeenCalled();
  });
});
