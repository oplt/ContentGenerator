import * as React from "react";
import { cn } from "../../lib/utils";

// DESIGN.md: minimal styling, warm border (hsl border token), near-zero radius
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      style={{ borderRadius: "var(--radius-sm)" }}
      className={cn(
        "flex h-11 w-full border border-input bg-input px-3 py-2 text-sm text-foreground transition",
        "placeholder:text-muted-foreground",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";
