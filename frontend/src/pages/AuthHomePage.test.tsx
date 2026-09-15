import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AuthHomePage from "./AuthHomePage";
import { renderWithProviders } from "../test/renderWithProviders";

const forgotPassword = vi.fn().mockResolvedValue(undefined);
const signInWithPassword = vi.fn().mockResolvedValue(undefined);
const signUpWithPassword = vi.fn().mockResolvedValue({
  requires_email_verification: true,
  message: "If the account can be registered, a verification email will be sent.",
});
const getAppConfig = vi.fn().mockResolvedValue({
  mfa_access: false,
  multi_account_mode: "on",
  multi_account_canary_percent: 0,
});

vi.mock("../api/auth", () => ({
  forgotPassword: (...args: unknown[]) => forgotPassword(...args),
}));

vi.mock("../api/health", () => ({
  getAppConfig: (...args: unknown[]) => getAppConfig(...args),
}));

vi.mock("../features/auth/AuthContext", () => ({
  useAuth: () => ({
    signInWithPassword,
    signUpWithPassword,
  }),
}));

describe("AuthHomePage", () => {
  beforeEach(() => {
    forgotPassword.mockClear();
    signInWithPassword.mockClear();
    signUpWithPassword.mockClear();
    getAppConfig.mockClear();
  });

  it("restores password visibility toggle and forgot-password reset request", async () => {
    const user = userEvent.setup();

    renderWithProviders(<AuthHomePage />);

    const passwordInput = screen.getByLabelText("Password");
    expect(passwordInput).toHaveAttribute("type", "password");

    await user.click(screen.getByRole("button", { name: "Show password" }));
    expect(passwordInput).toHaveAttribute("type", "text");

    await user.type(screen.getByLabelText("Email"), "demo@example.com");
    await user.click(screen.getByRole("button", { name: "Forgot password?" }));
    await user.click(screen.getByRole("button", { name: "Send reset link" }));

    expect(forgotPassword).toHaveBeenCalledWith({ email: "demo@example.com" });
    expect(
      screen.getByText("If that email exists, a reset link has been sent. Check your inbox.")
    ).toBeInTheDocument();
  });

  it("masks sign-in failures with a generic message", async () => {
    signInWithPassword.mockRejectedValueOnce(new Error("User not found"));
    const user = userEvent.setup();

    renderWithProviders(<AuthHomePage />);

    await user.type(screen.getByLabelText("Email"), "demo@example.com");
    await user.type(screen.getByLabelText("Password"), "wrong-password");
    await user.click(screen.getByRole("button", { name: "Sign In" }));

    expect(
      await screen.findByText("We couldn't sign you in with those credentials. Check your details and try again.")
    ).toBeInTheDocument();
  });

  it("sends stay-logged-in preference on sign-in", async () => {
    const user = userEvent.setup();

    renderWithProviders(<AuthHomePage />);

    const stayLoggedIn = screen.getByRole("checkbox", { name: /Stay logged in on this browser/i });
    expect(stayLoggedIn).toBeChecked();

    await user.type(screen.getByLabelText("Email"), "demo@example.com");
    await user.type(screen.getByLabelText("Password"), "password1234");
    await user.click(stayLoggedIn);
    await user.click(screen.getByRole("button", { name: "Sign In" }));

    expect(signInWithPassword).toHaveBeenCalledWith(
      expect.objectContaining({
        email: "demo@example.com",
        password: "password1234",
        remember_me: false,
      })
    );
  });

  it("shows a generic sign-up verification message", async () => {
    const user = userEvent.setup();

    renderWithProviders(<AuthHomePage />);

    await user.click(screen.getByRole("tab", { name: "Sign Up" }));
    await user.type(screen.getByLabelText("Email"), "demo@example.com");
    await user.type(screen.getByLabelText("Password"), "password1234");
    await user.click(screen.getByRole("button", { name: "Create Account" }));

    expect(
      await screen.findByText("If the account can be registered, a verification email will be sent.")
    ).toBeInTheDocument();
  });
});
