import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

// DESIGN.md — sentence case, restrained, 4px radius
const badgeVariants = cva(
  "inline-flex items-center rounded border px-2 py-0.5 text-xs font-medium tracking-normal",
  {
    variants: {
      variant: {
        default: "border-transparent bg-primary text-primary-foreground",
        muted: "border-border bg-muted text-muted-foreground",
        success: "border-transparent bg-success/15 text-success",
        warning: "border-transparent bg-warning/15 text-warning",
        danger: "border-transparent bg-destructive/15 text-destructive",
      },
    },
    defaultVariants: {
      variant: "default",
    },
  }
);

export function Badge({
  className,
  variant,
  ...props
}: React.HTMLAttributes<HTMLDivElement> & VariantProps<typeof badgeVariants>) {
  return <div className={cn(badgeVariants({ variant }), className)} {...props} />;
}
