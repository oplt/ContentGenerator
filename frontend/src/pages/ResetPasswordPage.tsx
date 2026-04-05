import { type InputHTMLAttributes, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { resetPassword } from "../api/auth";
import { Button } from "../components/ui/button";
import { Card } from "../components/ui/card";
import { Input } from "../components/ui/input";
import { cn } from "../lib/utils";

const schema = z
  .object({
    password: z.string().min(8, "Password must be at least 8 characters"),
    confirm_password: z.string(),
  })
  .refine((data) => data.password === data.confirm_password, {
    message: "Passwords do not match",
    path: ["confirm_password"],
  });

type Values = z.infer<typeof schema>;

function Field({
  label,
  error,
  ...props
}: InputHTMLAttributes<HTMLInputElement> & { label: string; error?: string }) {
  return (
    <label className="grid gap-2 text-sm font-medium text-foreground">
      <span>{label}</span>
      <Input
        {...props}
        className={cn(error && "border-destructive/60 focus-visible:ring-destructive", props.className)}
      />
      {error ? <span className="text-xs font-normal text-destructive">{error}</span> : null}
    </label>
  );
}

function Message({ kind, children }: { kind: "error" | "success" | "info"; children: string }) {
  return (
    <div
      className={cn(
        "rounded-xl border px-4 py-3 text-sm",
        kind === "error" && "border-destructive/30 bg-destructive/5 text-destructive",
        kind === "success" && "border-primary/20 bg-primary/5 text-primary",
        kind === "info" && "border-border bg-muted/40 text-muted-foreground"
      )}
    >
      {children}
    </div>
  );
}

export default function ResetPasswordPage() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const [serverError, setServerError] = useState<string | null>(null);
  const [done, setDone] = useState(false);
  const form = useForm<Values>({
    resolver: zodResolver(schema),
    defaultValues: { password: "", confirm_password: "" },
  });

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-lg p-8">
        <p className="text-xs uppercase tracking-[0.16em] text-primary">Account recovery</p>
        <h1 className="mt-3 text-2xl font-semibold">Reset your password</h1>
        <p className="mt-2 text-sm text-muted-foreground">
          Choose a new password, then return to sign in with the updated credentials.
        </p>

        <div className="mt-6 grid gap-4">
          {!token ? <Message kind="info">No reset token was found. Use the link sent to your email.</Message> : null}
          {serverError ? <Message kind="error">{serverError}</Message> : null}
          {done ? (
            <>
              <Message kind="success">Password reset successfully. You can sign in now.</Message>
              <Button asChild className="w-full">
                <Link to="/">Return to sign in</Link>
              </Button>
            </>
          ) : (
            <form
              className="grid gap-4"
              onSubmit={form.handleSubmit(async (values) => {
                if (!token) {
                  setServerError("Missing reset token.");
                  return;
                }

                try {
                  setServerError(null);
                  await resetPassword({ token, new_password: values.password });
                  setDone(true);
                } catch (submitError) {
                  setServerError((submitError as Error).message);
                }
              })}
            >
              <Field
                label="New password"
                type="password"
                autoComplete="new-password"
                placeholder="Create a new password"
                error={form.formState.errors.password?.message}
                {...form.register("password")}
              />
              <Field
                label="Confirm new password"
                type="password"
                autoComplete="new-password"
                placeholder="Repeat the new password"
                error={form.formState.errors.confirm_password?.message}
                {...form.register("confirm_password")}
              />
              <Button type="submit" className="w-full" disabled={form.formState.isSubmitting || !token}>
                {form.formState.isSubmitting ? "Resetting..." : "Reset password"}
              </Button>
            </form>
          )}
        </div>
      </Card>
    </div>
  );
}
