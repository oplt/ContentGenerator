import { cn } from "../../lib/utils";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "panel-gradient rounded-[1.5rem] border border-border/60 bg-card/80 text-card-foreground shadow-soft backdrop-blur",
        className
      )}
      {...props}
    />
  );
}
