import { cn } from "../../lib/utils";

// DESIGN.md: flat warm surface (cream bg), near-zero radius, warm amber shadow
// No glassmorphism, no gradient, no backdrop-blur — containers defined by bg color
export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "bg-card text-card-foreground shadow-card",
        className
      )}
      style={{ borderRadius: "var(--radius-card)" }}
      {...props}
    />
  );
}
