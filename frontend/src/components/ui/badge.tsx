import { cva, type VariantProps } from "class-variance-authority";
import { cn } from "../../lib/utils";

const badgeVariants = cva(
  "inline-flex items-center rounded-full border px-2.5 py-1 text-xs font-medium uppercase tracking-[0.16em]",
  {
    variants: {
      variant: {
        default: "border-primary/20 bg-primary/10 text-primary",
        muted: "border-border bg-muted text-muted-foreground",
        success: "border-emerald-400/30 bg-emerald-400/10 text-emerald-500",
        warning: "border-amber-400/30 bg-amber-400/10 text-amber-500",
        danger: "border-rose-400/30 bg-rose-400/10 text-rose-500",
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
