import { useState } from "react";
import { Link, Navigate } from "react-router-dom";
import { enableMfa, verifyMfa, type MfaEnableResponse } from "../api/auth";
import { useAuth } from "../features/auth/AuthContext";
import { canAccessAdminRoutes, requiresAdminMfa, requiresEmailVerification } from "../features/auth/access";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";

export default function MfaSetupPage() {
  const { isReady, isAuthenticated, currentUser, reloadSession, signOut } = useAuth();
  const [enrollment, setEnrollment] = useState<MfaEnableResponse | null>(null);
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState(false);

  if (!isReady) {
    return null;
  }
  if (!isAuthenticated) {
    return <Navigate to="/" replace />;
  }
  if (requiresEmailVerification(currentUser)) {
    return <Navigate to="/verify-email" replace />;
  }
  if (currentUser?.mfa_enabled && !requiresAdminMfa(currentUser)) {
    return <Navigate to="/dashboard" replace />;
  }

  const startEnrollment = async () => {
    setBusy(true);
    setError(null);
    try {
      const result = await enableMfa();
      setEnrollment(result);
    } catch {
      setError("Could not start MFA enrollment. Try again.");
    } finally {
      setBusy(false);
    }
  };

  const confirmEnrollment = async () => {
    if (code.trim().length !== 6) {
      setError("Enter the 6-digit code from your authenticator app.");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await verifyMfa({ code: code.trim() });
      await reloadSession();
      setDone(true);
    } catch {
      setError("Invalid or expired code. Start again if the setup session timed out.");
    } finally {
      setBusy(false);
    }
  };

  if (done || (currentUser && canAccessAdminRoutes(currentUser))) {
    return (
      <div className="flex min-h-screen items-center justify-center p-4">
        <Card className="max-w-lg space-y-4 p-8">
          <h1 className="text-2xl font-semibold">MFA enabled</h1>
          <p className="text-sm text-muted-foreground">
            Admin routes are unlocked for this session. Keep your authenticator app available for future sign-ins.
          </p>
          <Button asChild className="w-full">
            <Link to="/dashboard">Continue to dashboard</Link>
          </Button>
        </Card>
      </div>
    );
  }

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="max-w-lg space-y-5 p-8">
        <div>
          <h1 className="text-2xl font-semibold">Enable multi-factor authentication</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Admin accounts must enroll a TOTP authenticator before accessing the workspace.
          </p>
        </div>

        {!enrollment ? (
          <Button className="w-full" disabled={busy} onClick={() => void startEnrollment()}>
            {busy ? "Preparing…" : "Start MFA enrollment"}
          </Button>
        ) : (
          <div className="space-y-4">
            <div className="rounded-xl border border-border bg-muted/30 px-4 py-3 text-sm">
              <p className="font-medium">Add this account in your authenticator app</p>
              <p className="mt-2 break-all text-xs text-muted-foreground">{enrollment.provisioning_uri}</p>
              <p className="mt-3 text-xs font-medium text-muted-foreground">Manual secret</p>
              <p className="mt-1 font-mono text-sm">{enrollment.secret}</p>
            </div>
            <div className="space-y-2">
              <label className="text-sm font-medium" htmlFor="mfa-code">
                Verification code
              </label>
              <Input
                id="mfa-code"
                inputMode="numeric"
                autoComplete="one-time-code"
                maxLength={6}
                value={code}
                onChange={(event) => setCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                placeholder="123456"
              />
            </div>
            <Button className="w-full" disabled={busy} onClick={() => void confirmEnrollment()}>
              {busy ? "Verifying…" : "Confirm and enable MFA"}
            </Button>
          </div>
        )}

        {error ? <p className="text-sm text-destructive">{error}</p> : null}

        <div className="flex flex-col gap-2 sm:flex-row">
          <Button asChild variant="outline" className="w-full">
            <Link to="/">Return to sign in</Link>
          </Button>
          <Button
            variant="outline"
            className="w-full"
            onClick={() => {
              void signOut();
            }}
          >
            Sign out
          </Button>
        </div>
      </Card>
    </div>
  );
}
