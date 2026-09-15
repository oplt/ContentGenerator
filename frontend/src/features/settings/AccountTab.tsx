import { useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useForm } from "react-hook-form";
import { Link } from "react-router-dom";
import { disableMfa, enableMfa, verifyMfa } from "../../api/auth";
import {
  changeMyPassword,
  getMyProfile,
  listMySessions,
  revokeMySession,
  updateMyProfile,
} from "../../api/users";
import { useAuth } from "../auth/AuthContext";
import { Button } from "../../components/ui/button";
import { Card } from "../../components/ui/card";
import { Input } from "../../components/ui/input";
import { PasswordInput } from "../../components/ui/PasswordInput";
import { LoadingState } from "../../components/ui/LoadingState";
import { queryClient } from "../../lib/queryClient";
import { queryKeys } from "../../lib/queryKeys";

type ProfileForm = { full_name: string };
type PasswordForm = { current_password: string; new_password: string };

export function AccountTab() {
  const { currentUser, reloadSession } = useAuth();
  const [mfaSecret, setMfaSecret] = useState<{ secret: string; provisioning_uri: string } | null>(null);
  const [mfaCode, setMfaCode] = useState("");
  const [disableCode, setDisableCode] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const profile = useQuery({
    queryKey: queryKeys.userProfile,
    queryFn: getMyProfile,
  });
  const sessions = useQuery({
    queryKey: queryKeys.userSessions,
    queryFn: listMySessions,
  });

  const profileForm = useForm<ProfileForm>({
    values: { full_name: profile.data?.full_name ?? currentUser?.full_name ?? "" },
  });
  const passwordForm = useForm<PasswordForm>({
    defaultValues: { current_password: "", new_password: "" },
  });

  const updateProfileMutation = useMutation({
    mutationFn: (data: ProfileForm) => updateMyProfile({ full_name: data.full_name || null }),
    onSuccess: async () => {
      setMessage("Profile updated.");
      setError(null);
      await reloadSession();
      await queryClient.invalidateQueries({ queryKey: queryKeys.userProfile });
    },
    onError: () => setError("Could not update profile."),
  });

  const passwordMutation = useMutation({
    mutationFn: (data: PasswordForm) => changeMyPassword(data),
    onSuccess: () => {
      setMessage("Password changed.");
      setError(null);
      passwordForm.reset();
    },
    onError: () => setError("Could not change password."),
  });

  const revokeMutation = useMutation({
    mutationFn: revokeMySession,
    onSuccess: async () => {
      await queryClient.invalidateQueries({ queryKey: queryKeys.userSessions });
    },
  });

  if (profile.isLoading) {
    return <LoadingState label="Loading account" />;
  }

  const mfaEnabled = Boolean(currentUser?.mfa_enabled || profile.data?.mfa_enabled);

  return (
    <div className="space-y-6">
      <Card className="p-6">
        <h2 className="text-lg font-semibold">Account & security</h2>
        <p className="mt-1 text-sm text-muted-foreground">
          Manage your profile, password, sessions, and multi-factor authentication.
        </p>
        {message ? <p className="mt-3 text-sm text-foreground">{message}</p> : null}
        {error ? <p className="mt-3 text-sm text-destructive">{error}</p> : null}
      </Card>

      <Card className="space-y-4 p-6">
        <h2 className="text-lg font-semibold">Profile</h2>
        <p className="text-sm text-muted-foreground">{profile.data?.email ?? currentUser?.email}</p>
        <form
          className="flex flex-wrap items-end gap-3"
          onSubmit={profileForm.handleSubmit((data) => updateProfileMutation.mutate(data))}
        >
          <div className="min-w-[240px] flex-1 space-y-1">
            <label className="text-sm font-medium" htmlFor="full-name">
              Full name
            </label>
            <Input id="full-name" {...profileForm.register("full_name")} />
          </div>
          <Button type="submit" disabled={updateProfileMutation.isPending}>
            {updateProfileMutation.isPending ? "Saving…" : "Save profile"}
          </Button>
        </form>
      </Card>

      <Card className="space-y-4 p-6">
        <h2 className="text-lg font-semibold">Password</h2>
        <form
          className="grid gap-3 md:grid-cols-2"
          onSubmit={passwordForm.handleSubmit((data) => passwordMutation.mutate(data))}
        >
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="current-password">
              Current password
            </label>
            <PasswordInput
              id="current-password"
              {...passwordForm.register("current_password", { required: true, minLength: 8 })}
            />
          </div>
          <div className="space-y-1">
            <label className="text-sm font-medium" htmlFor="new-password">
              New password
            </label>
            <PasswordInput
              id="new-password"
              {...passwordForm.register("new_password", { required: true, minLength: 8 })}
            />
          </div>
          <Button type="submit" disabled={passwordMutation.isPending} className="md:col-span-2 w-fit">
            {passwordMutation.isPending ? "Updating…" : "Change password"}
          </Button>
        </form>
      </Card>

      <Card className="space-y-4 p-6">
        <h2 className="text-lg font-semibold">Multi-factor authentication</h2>
        <p className="text-sm text-muted-foreground">Status: {mfaEnabled ? "Enabled" : "Disabled"}</p>
        {!mfaEnabled ? (
          <div className="space-y-3">
            {!mfaSecret ? (
              <Button
                onClick={async () => {
                  try {
                    const result = await enableMfa();
                    setMfaSecret(result);
                    setError(null);
                  } catch {
                    setError("Could not start MFA enrollment.");
                  }
                }}
              >
                Start MFA enrollment
              </Button>
            ) : (
              <>
                <p className="break-all text-xs text-muted-foreground">{mfaSecret.provisioning_uri}</p>
                <p className="font-mono text-sm">{mfaSecret.secret}</p>
                <Input
                  value={mfaCode}
                  maxLength={6}
                  placeholder="123456"
                  onChange={(event) => setMfaCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
                />
                <Button
                  onClick={async () => {
                    try {
                      await verifyMfa({ code: mfaCode });
                      await reloadSession();
                      setMessage("MFA enabled.");
                      setError(null);
                      setMfaSecret(null);
                      setMfaCode("");
                    } catch {
                      setError("Invalid MFA code.");
                    }
                  }}
                >
                  Confirm MFA
                </Button>
              </>
            )}
            <Button asChild variant="outline">
              <Link to="/mfa-setup">Open dedicated MFA setup</Link>
            </Button>
          </div>
        ) : (
          <div className="flex flex-wrap items-end gap-3">
            <Input
              className="max-w-xs"
              value={disableCode}
              maxLength={6}
              placeholder="Authenticator code"
              onChange={(event) => setDisableCode(event.target.value.replace(/\D/g, "").slice(0, 6))}
            />
            <Button
              variant="outline"
              onClick={async () => {
                try {
                  await disableMfa({ code: disableCode });
                  await reloadSession();
                  setDisableCode("");
                  setMessage("MFA disabled.");
                  setError(null);
                } catch {
                  setError("Could not disable MFA.");
                }
              }}
            >
              Disable MFA
            </Button>
          </div>
        )}
      </Card>

      <Card className="space-y-4 p-6">
        <h2 className="text-lg font-semibold">Active sessions</h2>
        {sessions.isLoading ? (
          <LoadingState label="Loading sessions" />
        ) : (
          <div className="space-y-3">
            {(sessions.data ?? []).map((session) => (
              <div
                key={session.id}
                className="flex flex-wrap items-center justify-between gap-3 border-b border-border pb-3"
              >
                <div className="text-sm">
                  <p className="font-medium">{session.id.slice(0, 8)}…</p>
                  <p className="text-muted-foreground">
                    Created {new Date(session.created_at).toLocaleString()} · Expires{" "}
                    {new Date(session.expires_at).toLocaleString()}
                  </p>
                </div>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={revokeMutation.isPending}
                  onClick={() => revokeMutation.mutate(session.id)}
                >
                  Revoke
                </Button>
              </div>
            ))}
            {(sessions.data ?? []).length === 0 ? (
              <p className="text-sm text-muted-foreground">No active sessions listed.</p>
            ) : null}
          </div>
        )}
      </Card>
    </div>
  );
}
