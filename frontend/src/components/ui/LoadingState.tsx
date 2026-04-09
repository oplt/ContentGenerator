export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <div
        className="border border-border bg-card px-5 py-2 text-sm uppercase tracking-wider text-muted-foreground shadow-card"
        style={{ borderRadius: "var(--radius-sm)" }}
      >
        {label}…
      </div>
    </div>
  );
}
