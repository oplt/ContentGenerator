import * as TooltipPrimitive from "@radix-ui/react-tooltip";
import { CircleHelp } from "lucide-react";
import type { ReactNode } from "react";
import { cn } from "../../lib/utils";

type HelpSide = "top" | "right" | "bottom" | "left";

/**
 * Compact help affordance for secondary copy.
 * Never put critical validation or destructive warnings here — keep those visible.
 * Assumes a single app-level TooltipProvider (see AppProviders).
 */
export function HelpTooltip({
 content,
 label = "More information",
 children,
 side = "top",
}: {
 content: ReactNode;
 /** Accessible name for the trigger (screen readers). */
 label?: string;
 children?: ReactNode;
 side?: HelpSide;
}) {
 return (
 <TooltipPrimitive.Root>
 <TooltipPrimitive.Trigger asChild>
 <button
 type="button"
 className="inline-flex size-7 shrink-0 items-center justify-center text-muted-foreground transition hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
 style={{ borderRadius: "var(--radius-sm)" }}
 aria-label={label}
 >
 {children ?? <CircleHelp className="size-3.5" aria-hidden />}
 </button>
 </TooltipPrimitive.Trigger>
 <TooltipPrimitive.Portal>
 <TooltipPrimitive.Content
 side={side}
 sideOffset={6}
 className="z-50 max-w-xs border border-border bg-card px-3 py-2 text-xs leading-relaxed text-foreground "
 style={{ borderRadius: "var(--radius-sm)" }}
 >
 {content}
 <TooltipPrimitive.Arrow className="fill-card" />
 </TooltipPrimitive.Content>
 </TooltipPrimitive.Portal>
 </TooltipPrimitive.Root>
 );
}

/** Inline field-level help icon (hover + keyboard focus). */
export function FieldHelp({
 content,
 label = "Field help",
 side = "top",
}: {
 content: ReactNode;
 label?: string;
 side?: HelpSide;
}) {
 return <HelpTooltip content={content} label={label} side={side} />;
}

/**
 * Progressive disclosure for longer optional section explanations.
 * Keep page purpose, labels, validation errors, and dangerous warnings outside.
 */
export function SectionHelp({
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

/** @deprecated Prefer SectionHelp — kept for existing imports. */
export const HelpDisclosure = SectionHelp;

/** Compact form row: label + optional FieldHelp + control + visible error. */
export function FormField({
 label,
 htmlFor,
 help,
 error,
 className,
 children,
}: {
 label: string;
 htmlFor?: string;
 help?: ReactNode;
 error?: string;
 className?: string;
 children: ReactNode;
}) {
 return (
 <div className={cn("space-y-1.5 text-sm", className)}>
 <div className="flex items-center gap-1.5">
 <label htmlFor={htmlFor} className="font-medium leading-none">
 {label}
 </label>
 {help ? <FieldHelp content={help} label={`Help: ${label}`} /> : null}
 </div>
 {children}
 {error ? (
 <p className="text-xs text-destructive" role="alert">
 {error}
 </p>
 ) : null}
 </div>
 );
}
