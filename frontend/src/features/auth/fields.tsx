import { type InputHTMLAttributes, useId, useState } from "react";
import { Eye, EyeOff } from "lucide-react";
import { Input } from "../../components/ui/input";
import { cn } from "../../lib/utils";

type FormFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  error?: string;
};

export function FormField({ label, error, className, ...props }: FormFieldProps) {
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

export function PasswordField({ label, error, className, ...props }: FormFieldProps) {
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

export function StatusMessage({
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

