import { useEffect, useId, useRef } from "react";
import { NavLink } from "react-router-dom";
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "../../lib/utils";
import { useNavRoutes } from "../../navigation/useNavRoutes";

export function MobileNavDrawer({
  open,
  onOpenChange,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}) {
  const routes = useNavRoutes();
  const titleId = useId();
  const closeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    if (open) {
      window.requestAnimationFrame(() => closeRef.current?.focus());
    }
  }, [open]);

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-overlay/65 lg:hidden" />
        <DialogPrimitive.Content
          id="mobile-nav-drawer"
          aria-describedby={undefined}
          className={cn(
            "fixed inset-y-0 left-0 z-50 flex w-[min(92vw,20rem)] flex-col border-r border-border bg-background p-4 outline-none lg:hidden"
          )}
          onCloseAutoFocus={(event) => {
            // Topbar restores focus to the menu trigger.
            event.preventDefault();
          }}
        >
          <div className="flex items-start justify-between gap-3 px-2 pb-4">
            <div>
              <DialogPrimitive.Title id={titleId} className="text-sm font-medium tracking-[0.2em]">
                SIGNALFORGE
              </DialogPrimitive.Title>
              <p className="mt-1 text-sm text-muted-foreground">Navigate</p>
            </div>
            <DialogPrimitive.Close
              ref={closeRef}
              aria-label="Close navigation menu"
              className="inline-flex min-h-10 min-w-10 items-center justify-center rounded border border-border text-muted-foreground transition-colors duration-300 hover:bg-muted"
            >
              <X className="size-4" aria-hidden />
            </DialogPrimitive.Close>
          </div>

          <nav aria-label="Mobile primary" className="flex-1 space-y-0.5 overflow-y-auto">
            {routes.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.end}
                onClick={() => onOpenChange(false)}
                className={({ isActive }) =>
                  cn(
                    "flex min-h-11 items-center gap-3 px-3 py-2.5 text-sm transition-colors",
                    isActive
                      ? "bg-foreground text-background"
                      : "text-muted-foreground hover:bg-muted hover:text-foreground"
                  )
                }
                style={{ borderRadius: "var(--radius-sm)" }}
              >
                <item.icon className="size-4 shrink-0" aria-hidden />
                {item.label}
              </NavLink>
            ))}
          </nav>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
