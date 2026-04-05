export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <div className="rounded-full border border-border bg-card px-4 py-2 text-sm text-muted-foreground shadow-soft">
        {label}...
      </div>
    </div>
  );
}
