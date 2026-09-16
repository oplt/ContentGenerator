/** Compact list skeleton — prefer over full-viewport LoadingState for catalog panels. */
export function ChessListSkeleton({
  rows = 4,
  label = "Loading",
}: {
  rows?: number;
  label?: string;
}) {
  return (
    <div className="grid gap-2" role="status" aria-busy="true" aria-label={label}>
      {Array.from({ length: rows }, (_, index) => (
        <div
          key={index}
          className="flex animate-pulse gap-3 rounded border border-border bg-card p-3"
        >
          <div className="size-14 shrink-0 rounded bg-muted" />
          <div className="min-w-0 flex-1 space-y-2 py-1">
            <div className="h-3.5 w-2/3 rounded bg-muted" />
            <div className="h-3 w-1/2 rounded bg-muted" />
            <div className="h-3 w-1/3 rounded bg-muted" />
          </div>
        </div>
      ))}
      <span className="sr-only">{label}…</span>
    </div>
  );
}
