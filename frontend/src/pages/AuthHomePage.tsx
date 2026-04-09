import { type InputHTMLAttributes, useId, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { useQuery } from "@tanstack/react-query";
import { Eye, EyeOff } from "lucide-react";
import { forgotPassword } from "../api/auth";
import { getAppConfig } from "../api/health";
import { useAuth } from "../features/auth/AuthContext";
import {
  forgotPasswordSchema,
  signInSchema,
  signUpSchema,
  type ForgotPasswordValues,
  type SignInValues,
  type SignUpValues,
} from "../features/auth/schemas";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { cn } from "../lib/utils";

const GENERIC_SIGN_IN_ERROR =
  "We couldn't sign you in with those credentials. Check your details and try again.";
const GENERIC_SIGN_UP_ERROR =
  "We couldn't complete sign up. Check your details, or reset your password if you already have an account.";
const GENERIC_FORGOT_PASSWORD_SUCCESS =
  "If that email exists, a reset link has been sent. Check your inbox.";

type AuthTab = "sign-in" | "sign-up";

type FormFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
};

function FormField({ label, error, className, ...props }: FormFieldProps) {
  const id = useId();

  return (
    <label className="grid gap-2 text-sm font-medium text-foreground" htmlFor={id}>
      <span>{label}</span>
      <Input
        {...props}
        id={id}
        className={cn(error && "border-destructive/60 focus-visible:ring-destructive", className)}
      />
      {error ? <span className="text-xs font-normal text-destructive">{error}</span> : null}
    </label>
  );
}

function PasswordField({ label, error, className, ...props }: FormFieldProps) {
  const id = useId();
  const [showPassword, setShowPassword] = useState(false);

  return (
    <label className="grid gap-2 text-sm font-medium text-foreground" htmlFor={id}>
      <span>{label}</span>
      <div className="relative">
        <Input
          {...props}
          id={id}
          type={showPassword ? "text" : "password"}
          className={cn(
            "pr-12",
            error && "border-destructive/60 focus-visible:ring-destructive",
            className
          )}
        />
        <button
          type="button"
          aria-label={showPassword ? "Hide password" : "Show password"}
          className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground transition hover:text-foreground"
          onClick={() => setShowPassword((value) => !value)}
        >
          {showPassword ? <EyeOff className="size-4" /> : <Eye className="size-4" />}
        </button>
      </div>
      {error ? <span className="text-xs font-normal text-destructive">{error}</span> : null}
    </label>
  );
}

function StatusMessage({
  variant,
  message,
}: {
  variant: "error" | "success";
  message: string;
}) {
  return (
    <div
      className={cn(
        "rounded-xl border px-4 py-3 text-sm",
        variant === "error"
          ? "border-destructive/30 bg-destructive/5 text-destructive"
          : "border-primary/20 bg-primary/5 text-primary"
      )}
    >
      {message}
    </div>
  );
}

export default function AuthHomePage() {
  const navigate = useNavigate();
  const { signInWithPassword, signUpWithPassword } = useAuth();
  const { data: appConfig } = useQuery({
    queryKey: ["app-config"],
    queryFn: getAppConfig,
    staleTime: Infinity,
  });
  const mfaEnabled = appConfig?.mfa_access ?? false;
  const [activeTab, setActiveTab] = useState<AuthTab>("sign-in");
  const [signInError, setSignInError] = useState<string | null>(null);
  const [signUpError, setSignUpError] = useState<string | null>(null);
  const [forgotPasswordOpen, setForgotPasswordOpen] = useState(false);
  const [forgotPasswordError, setForgotPasswordError] = useState<string | null>(null);
  const [forgotPasswordSuccess, setForgotPasswordSuccess] = useState<string | null>(null);
  const [signUpSuccess, setSignUpSuccess] = useState<string | null>(null);
  const signInForm = useForm<SignInValues>({
    resolver: zodResolver(signInSchema),
    defaultValues: { email: "", password: "", mfa_code: "" },
  });
  const signUpForm = useForm<SignUpValues>({
    resolver: zodResolver(signUpSchema),
    defaultValues: { full_name: "", email: "", password: "" },
  });
  const forgotPasswordForm = useForm<ForgotPasswordValues>({
    resolver: zodResolver(forgotPasswordSchema),
    defaultValues: { email: "" },
  });

  function resetPanelState(nextTab: AuthTab) {
    setActiveTab(nextTab);
    setSignInError(null);
    setSignUpError(null);
    setSignUpSuccess(null);
    setForgotPasswordOpen(false);
    setForgotPasswordError(null);
    setForgotPasswordSuccess(null);
  }

  return (
    <div className="grid min-h-screen lg:grid-cols-[1.1fr,0.9fr]">
      {/* Left - warm Mistral gradient hero */}
      <div
        className="hidden px-10 py-12 text-white lg:flex lg:flex-col lg:justify-between"
        style={{
          background:
            "linear-gradient(160deg, #fffaeb 0%, #fff0c2 18%, #ffa110 48%, #fa520f 68%, #1f1f1f 100%)",
        }}
      >
        <div>
          {/* Block gradient identity strip */}
          <div className="h-1 w-24 block-gradient mb-6" />
          <p className="eyebrow text-[#1f1f1f]">SignalForge</p>
          <h1
            className="mt-6 max-w-xl text-[#1f1f1f]"
            style={{ fontSize: "3.5rem", lineHeight: 0.95, fontWeight: 400 }}
          >
            Turn live news signals into approved multi-platform content operations.
          </h1>
          <p className="mt-6 max-w-xl text-lg text-white/80">
            Ingest, score, brief, approve in Telegram, publish, and track analytics from one tenant-aware editorial control center.
          </p>
        </div>
        <div className="grid gap-3 md:grid-cols-3">
          {["Signal ingestion", "Editorial approvals", "Publishing + analytics"].map((item) => (
            <div
              key={item}
              className="border border-white/20 bg-white/10 p-4"
              style={{ borderRadius: "var(--radius-sm)" }}
            >
              <p className="text-sm uppercase tracking-wider text-white/90">{item}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Right - auth form on warm ivory */}
      <div className="flex items-center justify-center bg-background px-4 py-10">
        <Card className="w-full max-w-md p-6">
          <p className="eyebrow text-primary">Workspace access</p>
          <h2 className="mt-3 text-2xl">Authenticate to your dashboard</h2>
          <p className="mt-2 text-sm text-muted-foreground">
            Sign in to continue, or create a new workspace account.
          </p>
          <Tabs
            value={activeTab}
            onValueChange={(value) => resetPanelState(value as AuthTab)}
            className="mt-6"
          >
            <TabsList className="grid w-full grid-cols-2">
              <TabsTrigger value="sign-in">Sign In</TabsTrigger>
              <TabsTrigger value="sign-up">Sign Up</TabsTrigger>
            </TabsList>
            <TabsContent value="sign-in" className="mt-4">
              {signInError ? <StatusMessage variant="error" message={signInError} /> : null}
              <form
                className="mt-4 grid gap-4"
                onSubmit={signInForm.handleSubmit(async (values) => {
                  try {
                    setSignInError(null);
                    await signInWithPassword(values);
                    navigate("/dashboard");
                  } catch (submitError) {
                    if (submitError instanceof TypeError) {
                      setSignInError("We couldn't reach the server. Try again.");
                      return;
                    }
                    setSignInError(GENERIC_SIGN_IN_ERROR);
                  }
                })}
              >
                <FormField
                  label="Email"
                  type="email"
                  placeholder="you@example.com"
                  autoComplete="email"
                  error={signInForm.formState.errors.email?.message}
                  {...signInForm.register("email")}
                />
                <PasswordField
                  label="Password"
                  placeholder="Enter your password"
                  autoComplete="current-password"
                  error={signInForm.formState.errors.password?.message}
                  {...signInForm.register("password")}
                />
                {mfaEnabled && (
                  <FormField
                    label="MFA code"
                    placeholder="6-digit code"
                    inputMode="numeric"
                    autoComplete="one-time-code"
                    error={signInForm.formState.errors.mfa_code?.message}
                    {...signInForm.register("mfa_code")}
                  />
                )}
                <Button type="submit" className="w-full" disabled={signInForm.formState.isSubmitting}>
                  {signInForm.formState.isSubmitting ? "Signing In..." : "Sign In"}
                </Button>
              </form>
              <button
                type="button"
                className="mt-4 text-sm font-medium text-primary transition hover:text-primary/80"
                onClick={() => {
                  const nextOpen = !forgotPasswordOpen;
                  setForgotPasswordOpen(nextOpen);
                  setForgotPasswordError(null);
                  setForgotPasswordSuccess(null);
                  if (nextOpen) {
                    forgotPasswordForm.reset({ email: signInForm.getValues("email") });
                  }
                }}
              >
                {forgotPasswordOpen ? "Hide password reset" : "Forgot password?"}
              </button>
              {forgotPasswordOpen ? (
                <div className="mt-4 rounded-2xl border border-border/70 bg-muted/30 p-4">
                  <p className="text-sm text-muted-foreground">
                    Enter the email for your account and we&apos;ll send a reset link.
                  </p>
                  {forgotPasswordError ? (
                    <div className="mt-3">
                      <StatusMessage variant="error" message={forgotPasswordError} />
                    </div>
                  ) : null}
                  {forgotPasswordSuccess ? (
                    <div className="mt-3">
                      <StatusMessage variant="success" message={forgotPasswordSuccess} />
                    </div>
                  ) : null}
                  <form
                    className="mt-4 grid gap-4"
                    onSubmit={forgotPasswordForm.handleSubmit(async (values) => {
                      try {
                        setForgotPasswordError(null);
                        setForgotPasswordSuccess(null);
                        await forgotPassword(values);
                        setForgotPasswordSuccess(GENERIC_FORGOT_PASSWORD_SUCCESS);
                      } catch (submitError) {
                        if (submitError instanceof TypeError) {
                          setForgotPasswordError("We couldn't reach the server. Try again.");
                          return;
                        }
                        setForgotPasswordSuccess(GENERIC_FORGOT_PASSWORD_SUCCESS);
                      }
                    })}
                  >
                    <FormField
                      label="Reset email"
                      type="email"
                      placeholder="you@example.com"
                      autoComplete="email"
                      error={forgotPasswordForm.formState.errors.email?.message}
                      {...forgotPasswordForm.register("email")}
                    />
                    <Button
                      type="submit"
                      variant="outline"
                      className="w-full"
                      disabled={forgotPasswordForm.formState.isSubmitting}
                    >
                      {forgotPasswordForm.formState.isSubmitting ? "Sending..." : "Send reset link"}
                    </Button>
                  </form>
                </div>
              ) : null}
            </TabsContent>
            <TabsContent value="sign-up" className="mt-4">
              {signUpSuccess ? <StatusMessage variant="success" message={signUpSuccess} /> : null}
              {signUpError ? <StatusMessage variant="error" message={signUpError} /> : null}
              <form
                className="mt-4 grid gap-4"
                onSubmit={signUpForm.handleSubmit(async (values) => {
                  try {
                    setSignUpError(null);
                    setSignUpSuccess(null);
                    const result = await signUpWithPassword(values);
                    setSignUpSuccess(
                      result.message ?? "If the account can be registered, a verification email will be sent."
                    );
                    signUpForm.reset({ full_name: "", email: "", password: "", admin_invite_code: "" });
                  } catch (submitError) {
                    if (submitError instanceof TypeError) {
                      setSignUpError("We couldn't reach the server. Try again.");
                      return;
                    }
                    setSignUpError(GENERIC_SIGN_UP_ERROR);
                  }
                })}
              >
                <FormField
                  label="Full name"
                  placeholder="Jane Smith"
                  autoComplete="name"
                  error={signUpForm.formState.errors.full_name?.message}
                  {...signUpForm.register("full_name")}
                />
                <FormField
                  label="Email"
                  type="email"
                  placeholder="you@example.com"
                  autoComplete="email"
                  error={signUpForm.formState.errors.email?.message}
                  {...signUpForm.register("email")}
                />
                <PasswordField
                  label="Password"
                  placeholder="Create a password"
                  autoComplete="new-password"
                  error={signUpForm.formState.errors.password?.message}
                  {...signUpForm.register("password")}
                />
                <Button type="submit" className="w-full" disabled={signUpForm.formState.isSubmitting}>
                  {signUpForm.formState.isSubmitting ? "Creating Account..." : "Create Account"}
                </Button>
              </form>
            </TabsContent>
          </Tabs>
        </Card>
      </div>
    </div>
  );
}
