export function LoadingState({ label = "Loading" }: { label?: string }) {
  return (
    <div className="flex min-h-[40vh] items-center justify-center">
      <div className="rounded border border-border bg-background px-5 py-2 text-sm font-medium text-muted-foreground">
        {label}…
      </div>
    </div>
  );
}
