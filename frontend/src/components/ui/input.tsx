import * as React from "react";
import { cn } from "../../lib/utils";

// DESIGN.md §4 — Carbon text, Silver Fog placeholder, 4px radius
export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...props }, ref) => (
    <input
      ref={ref}
      className={cn(
        "flex h-10 w-full rounded border border-border bg-background px-3 py-2 text-sm text-foreground",
        "placeholder:text-[#8E8E8E]",
        "transition-[border-color,box-shadow] duration-300",
        "focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
        "disabled:cursor-not-allowed disabled:opacity-50",
        className
      )}
      {...props}
    />
  )
);
Input.displayName = "Input";
