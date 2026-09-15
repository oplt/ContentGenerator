import { cn } from "../../lib/utils";

// DESIGN.md — flat white/ash surface, 4px radius, no shadow/glass
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded border border-border bg-card p-6 text-card-foreground", className)}
      {...props}
    />
  );
}
