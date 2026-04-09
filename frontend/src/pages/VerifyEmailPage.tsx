import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { verifyEmail } from "../api/auth";
import { useAuth } from "../features/auth/AuthContext";
import { canAccessAdminRoutes, requiresAdminMfa, requiresEmailVerification } from "../features/auth/access";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";

export default function VerifyEmailPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token");
  const required = searchParams.get("required");
  const { currentUser, reloadSession } = useAuth();
  const [status, setStatus] = useState<"idle" | "verifying" | "success" | "error">(
    token ? "verifying" : "idle"
  );
  const [message, setMessage] = useState<string | null>(null);

  useEffect(() => {
    if (!token) {
      return;
    }

    let active = true;

    verifyEmail({ token })
      .then(async () => {
        await reloadSession().catch(() => undefined);
        if (!active) {
          return;
        }
        setStatus("success");
        setMessage("Your email has been verified. You can continue to the dashboard.");
      })
      .catch(() => {
        if (!active) {
          return;
        }
        setStatus("error");
        setMessage("This verification link is invalid or expired. Request a new verification email.");
      });

    return () => {
      active = false;
    };
  }, [reloadSession, token]);

  const needsVerification = requiresEmailVerification(currentUser);
  const needsAdminMfa = requiresAdminMfa(currentUser) || required === "mfa";
  const verificationCompleted = status === "success";
  const canContinue = Boolean(
    (!needsVerification || verificationCompleted) &&
      (!currentUser || !currentUser.is_admin || canAccessAdminRoutes(currentUser) || verificationCompleted)
  );

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="max-w-lg p-8">
        <h1 className="text-2xl font-semibold">
          {needsAdminMfa ? "Additional account security required" : "Verify your email"}
        </h1>
        <p className="mt-3 text-sm text-muted-foreground">
          {needsAdminMfa
            ? "Admin access is blocked until multi-factor authentication is enabled for this account."
            : "Open the verification link from your inbox to finish activating the account before using the dashboard."}
        </p>

        <div className="mt-6 space-y-4">
          {status === "verifying" ? (
            <p className="text-sm text-muted-foreground">Verifying your email...</p>
          ) : null}
          {message ? (
            <p className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm">{message}</p>
          ) : null}
          {!token && needsVerification ? (
            <p className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm">
              Check your inbox and open the latest verification link. Full access stays blocked until verification completes.
            </p>
          ) : null}
          {needsAdminMfa ? (
            <p className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm">
              This frontend now blocks admin-only routes unless the session reports `mfa_enabled=true`. The MFA enrollment flow must be completed in the backend or identity provider.
            </p>
          ) : null}

          <div className="flex flex-col gap-3 sm:flex-row">
            {canContinue ? (
              <Button asChild className="w-full">
                <Link to="/dashboard">Continue to dashboard</Link>
              </Button>
            ) : (
              <Button asChild className="w-full">
                <Link to="/">Return to sign in</Link>
              </Button>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
