import { MemoryRouter } from "react-router-dom";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AuthHomePage from "./AuthHomePage";

const forgotPassword = vi.fn().mockResolvedValue(undefined);
const signInWithPassword = vi.fn().mockResolvedValue(undefined);
const signUpWithPassword = vi.fn().mockResolvedValue(undefined);

vi.mock("../api/auth", () => ({
  forgotPassword: (...args: unknown[]) => forgotPassword(...args),
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
  });

  it("restores password visibility toggle and forgot-password reset request", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter>
        <AuthHomePage />
      </MemoryRouter>
    );

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
});
