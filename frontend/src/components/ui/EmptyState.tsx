import { Sparkles } from "lucide-react";

export function EmptyState({ title, description }: { title: string; description: string }) {
  return (
    <div
      className="border border-dashed border-border bg-card/60 p-8 text-center"
      style={{ borderRadius: "var(--radius-card)" }}
    >
      <div
        className="mx-auto mb-4 flex size-12 items-center justify-center bg-primary/10 text-primary"
        style={{ borderRadius: "var(--radius-sm)" }}
      >
        <Sparkles className="size-5" />
      </div>
      <h3 className="text-lg">{title}</h3>
      <p className="mt-2 text-sm text-muted-foreground">{description}</p>
    </div>
  );
}
