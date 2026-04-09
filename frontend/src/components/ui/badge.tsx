import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

// DESIGN.md: uppercase labels, near-zero radius, warm palette
const badgeVariants = cva(
  "inline-flex items-center border px-2.5 py-1 text-xs font-normal uppercase tracking-[0.14em]",
  {
    variants: {
      variant: {
        default:     "border-primary/30  bg-primary/10  text-primary",
        muted:       "border-border       bg-muted        text-muted-foreground",
        success:     "border-success/30  bg-success/10  text-success",
        warning:     "border-warning/40  bg-warning/10  text-warning",
        danger:      "border-destructive/30 bg-destructive/10 text-destructive",
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
  return (
    <div
      className={cn(badgeVariants({ variant }), className)}
      style={{ borderRadius: "var(--radius-sm)" }}
      {...props}
    />
  );
}
