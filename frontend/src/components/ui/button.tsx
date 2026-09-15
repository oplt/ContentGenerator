import * as React from "react";
import { Slot } from "@radix-ui/react-slot";
import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

// DESIGN.md: weight 400 everywhere, uppercase CTAs, near-zero radius, no lift animation
const buttonVariants = cva(
  "inline-flex items-center justify-center gap-2 text-sm font-normal uppercase tracking-wider transition-all duration-200 disabled:pointer-events-none disabled:opacity-40",
  {
    variants: {
      variant: {
        // Dark Solid — DESIGN.md primary action: Mistral Black bg, white text
        default:
          "bg-foreground text-background hover:bg-foreground/85 hover:shadow-md",
        // Orange Brand — for brand-moment CTAs (sign in, plan & generate)
        primary:
          "bg-primary text-primary-foreground hover:bg-primary/85 hover:shadow-md",
        // Cream Surface — warm secondary CTA
        secondary:
          "bg-card text-foreground border border-border hover:bg-muted hover:shadow-md",
        // Ghost — de-emphasised action
        ghost:
          "text-foreground hover:bg-muted/60 hover:shadow-md",
        // Outline — bordered, transparent fill
        outline:
          "border border-foreground/25 bg-transparent text-foreground hover:bg-muted/50 hover:shadow-md",
        // Destructive
        destructive:
          "bg-destructive text-destructive-foreground hover:bg-destructive/85 hover:shadow-md",
      },
      size: {
        default: "h-11 px-5 py-3", // 12px padding from DESIGN.md
        sm: "h-9 px-3 py-2 text-xs",
        lg: "h-13 px-7 py-4 text-base",
        icon: "h-10 w-10",
      },
    },
    defaultVariants: {
      variant: "default",
      size: "default",
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
