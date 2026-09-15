import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

// DESIGN.md §4 — 4px radius, 14px/500, 0.33s color transitions, no uppercase, no lift
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 rounded text-sm font-medium transition-[color,background-color,border-color,box-shadow] duration-300 disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        default: "bg-foreground text-background hover:bg-foreground/90",
        primary: "bg-primary text-primary-foreground hover:bg-primary/90",
        secondary: "border border-border bg-background text-[#393C41] hover:bg-muted",
        ghost: "text-foreground hover:bg-muted",
        outline: "border border-border bg-transparent text-foreground hover:bg-muted",
        destructive: "bg-destructive text-destructive-foreground hover:bg-destructive/90",
      },
      size: {
        default: "h-10 min-h-10 px-4 py-2",
        sm: "h-8 px-3 text-xs",
        lg: "h-11 px-6",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export interface ButtonProps
  extends React.ButtonHTMLAttributes<HTMLButtonElement>,
  VariantProps<typeof buttonVariants> {
  asChild?: boolean;
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild = false, ...props }, ref) => {
    const Comp = asChild ? Slot : "button";
    return (
      <Comp
        className={cn(buttonVariants({ variant, size, className }))}
        ref={ref}
        {...props}
      />
    );
  }
);
Button.displayName = "Button";
