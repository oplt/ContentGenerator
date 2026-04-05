import * as DialogPrimitive from "@radix-ui/react-dialog";
import { X } from "lucide-react";
import { cn } from "../../lib/utils";

export function Dialog(props: DialogPrimitive.DialogProps) {
  return <DialogPrimitive.Root {...props} />;
}

export function DialogTrigger(props: DialogPrimitive.DialogTriggerProps) {
  return <DialogPrimitive.Trigger {...props} />;
}

export function DialogClose(props: DialogPrimitive.DialogCloseProps) {
  return <DialogPrimitive.Close {...props} />;
}

export function DialogContent({
  className,
  children,
  ...props
}: DialogPrimitive.DialogContentProps) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-40 bg-slate-950/60 backdrop-blur-sm" />
      <DialogPrimitive.Content
        className={cn(
          "fixed left-1/2 top-1/2 z-50 w-[min(92vw,760px)] -translate-x-1/2 -translate-y-1/2 rounded-[1.5rem] border border-border bg-card p-6 shadow-soft",
          className
        )}
        {...props}
      >
        {children}
        <DialogPrimitive.Close className="absolute right-4 top-4 rounded-full border border-border p-2 text-muted-foreground transition hover:bg-muted">
          <X className="size-4" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  );
}
