import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { CircleHelp } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

export function HelpTooltip({
  label,
  children,
  side = "top",
}: {
  label: string;
  children?: ReactNode;
  side?: "top" | "right" | "bottom" | "left";
}) {
  return (
    <TooltipPrimitive.Provider delayDuration={200}>
      <TooltipPrimitive.Root>
        <TooltipPrimitive.Trigger asChild>
          <button
            type="button"
            className="inline-flex size-8 items-center justify-center text-muted-foreground transition hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            style={{ borderRadius: "var(--radius-sm)" }}
            aria-label={label}
          >
            {children ?? <CircleHelp className="size-4" />}
          </button>
        </TooltipPrimitive.Trigger>
        <TooltipPrimitive.Portal>
          <TooltipPrimitive.Content
            side={side}
            sideOffset={6}
            className="z-50 max-w-xs border border-border bg-card px-3 py-2 text-xs text-foreground shadow-card"
            style={{ borderRadius: "var(--radius-sm)" }}
          >
            {label}
            <TooltipPrimitive.Arrow className="fill-card" />
          </TooltipPrimitive.Content>
        </TooltipPrimitive.Portal>
      </TooltipPrimitive.Root>
    </TooltipPrimitive.Provider>
  );
}

/** Progressive disclosure for longer optional explanations (keeps critical warnings outside). */
export function HelpDisclosure({
  summary,
  children,
  className,
  defaultOpen = false,
}: {
  summary: string;
  children: ReactNode;
  className?: string;
  defaultOpen?: boolean;
}) {
  return (
    <details
      className={cn("border border-border bg-muted/30 text-sm", className)}
      style={{ borderRadius: "var(--radius-sm)" }}
      open={defaultOpen || undefined}
    >
      <summary className="cursor-pointer list-none px-4 py-3 font-medium marker:content-none [&::-webkit-details-marker]:hidden">
        <span className="inline-flex items-center gap-2">
          <CircleHelp className="size-4 text-muted-foreground" aria-hidden />
          {summary}
        </span>
      </summary>
      <div className="border-t border-border px-4 py-3 text-muted-foreground">{children}</div>
    </details>
  );
}
