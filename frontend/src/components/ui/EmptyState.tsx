import { Sparkles } from "lucide-react";

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div className="rounded-[1.5rem] border border-dashed border-border bg-card/60 p-8 text-center">
      <div className="mx-auto mb-4 flex size-12 items-center justify-center rounded-2xl bg-primary/10 text-primary">
        <Sparkles className="size-5" />
      </div>
      <h3 className="text-lg font-semibold">{title}</h3>
      <p className="mt-2 text-sm text-muted-foreground">{description}</p>
    </div>
  );
}
